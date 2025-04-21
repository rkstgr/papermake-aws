use aws_lambda_events::sqs::SqsEvent;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use std::env;
use std::sync::Arc;
use std::collections::HashMap;
use tokio::sync::{RwLock, OnceCell, Mutex};
use thiserror::Error;
use papermake::typst::TypstWorld;

#[derive(Debug, Deserialize, Serialize)]
struct RenderJob {
    job_id: String,
    template_id: String,
    data: serde_json::Value,
}

#[derive(Error, Debug)]
pub enum RenderError {
    #[error("Failed to parse job: {0}")]
    JobParseError(String),
    #[error("Failed to render PDF: {0}")]
    RenderingError(String),
    #[error("S3 operation failed: {0}")]
    S3Error(String),
    #[error("Environment variable not found: {0}")]
    EnvVarError(String),
}

// Shared resources across invocations
#[derive(Debug)]
struct SharedResources {
    s3_client: aws_sdk_s3::Client,
    templates_bucket: String,
    results_bucket: String,
    template_cache: RwLock<HashMap<String, Vec<u8>>>,
    // Add world cache with Mutex because TypstWorld requires &mut self
    world_cache: RwLock<HashMap<String, Arc<Mutex<TypstWorld>>>>,
}

// Use OnceCell instead of Lazy to initialize asynchronously
static RESOURCES: OnceCell<Arc<SharedResources>> = OnceCell::const_new();

// Initialize resources asynchronously
async fn initialize_resources() -> Arc<SharedResources> {
    // Read environment variables
    let templates_bucket = env::var("TEMPLATES_BUCKET")
        .expect("TEMPLATES_BUCKET environment variable not set");
    let results_bucket = env::var("RESULTS_BUCKET")
        .expect("RESULTS_BUCKET environment variable not set");
    
    // Initialize AWS client
    let config = aws_config::load_from_env().await;
    let s3_client = aws_sdk_s3::Client::new(&config);
    
    // Create and return resources
    Arc::new(SharedResources {
        s3_client,
        templates_bucket,
        results_bucket,
        template_cache: RwLock::new(HashMap::new()),
        world_cache: RwLock::new(HashMap::new()),
    })
}

async fn function_handler(event: LambdaEvent<SqsEvent>) -> Result<(), Error> {
    // Get the shared resources
    let resources = RESOURCES.get().expect("Resources not initialized");

    println!("Batch size: {}", event.payload.records.len());
    
    // Process each message from SQS
    for record in event.payload.records {
        let message_body = record.body.as_ref()
            .ok_or_else(|| RenderError::JobParseError("Empty message body".to_string()))?;
            
        // Parse the job from the message
        let job: RenderJob = match serde_json::from_str(message_body) {
            Ok(job) => job,
            Err(e) => {
                eprintln!("Failed to parse job: {}", e);
                continue; // Skip this message and move to the next one
            }
        };
        
        println!("Processing job {}: template={}", job.job_id, job.template_id);

        // Try to get template from cache first
        let template_data = {
            let cache = resources.template_cache.read().await;
            cache.get(&job.template_id).cloned()
        };
        
        // If not in cache, fetch from S3 and cache it
        let template_data = match template_data {
            Some(data) => {
                println!("Using cached template for {}", job.template_id);
                data
            },
            None => {
                println!("Template {} not in cache, fetching from S3", job.template_id);
                // Get template from S3
                let template_result = resources.s3_client
                    .get_object()
                    .bucket(&resources.templates_bucket)
                    .key(&job.template_id)
                    .send()
                    .await;
                    
                let template = match template_result {
                    Ok(t) => t,
                    Err(e) => {
                        eprintln!("Failed to fetch template {}: {}", job.template_id, e);
                        continue;
                    }
                };

                let data = match template.body.collect().await {
                    Ok(data) => data.to_vec(),
                    Err(e) => {
                        eprintln!("Failed to read template data: {}", e);
                        continue;
                    }
                };
                
                // Cache the template
                {
                    let mut cache = resources.template_cache.write().await;
                    cache.insert(job.template_id.clone(), data.clone());
                }
                
                data
            }
        };
        
        // Check if we have a cached world for this template
        let world_cache_available = {
            let cache = resources.world_cache.read().await;
            cache.contains_key(&job.template_id)
        };
        
        // Render PDF using papermake with world caching
        let render_result = if world_cache_available {
            // Clone the mutex to extend its lifetime beyond the read lock
            let world_mutex = {
                let cache = resources.world_cache.read().await;
                cache.get(&job.template_id).unwrap().clone()
            };
            
            // Now we can lock it safely
            let mut world_guard = world_mutex.lock().await;
            
            println!("Using cached world for template {}", job.template_id);
            match render_pdf_with_cache(
                &job.template_id,
                &template_data.as_slice(),
                &job.data,
                Some(&mut *world_guard),
            ) {
                Ok(result) => result,
                Err(e) => {
                    eprintln!("Rendering error with cached world: {}", e);
                    continue;
                }
            }
        } else {
            // Render without cached world
            match render_pdf(
                &job.template_id,
                &template_data.as_slice(),
                &job.data,
            ) {
                Ok((result, world)) => {
                    // Cache the world for future use
                    if let Some(w) = world {
                        println!("Caching world for template {}", job.template_id);
                        let mut cache = resources.world_cache.write().await;
                        cache.insert(job.template_id.clone(), Arc::new(Mutex::new(w)));
                    }
                    result
                },
                Err(e) => {
                    eprintln!("Rendering error: {}", e);
                    continue;
                }
            }
        };

        if let None = render_result.pdf {
            eprintln!("Rendering result is None for job {}", job.job_id);
            continue;
        }

        let pdf = render_result.pdf.unwrap();

        // Upload PDF to S3
        match resources.s3_client
            .put_object()
            .bucket(&resources.results_bucket)
            .key(format!("{}.pdf", job.job_id))
            .body(pdf.into())
            .send()
            .await
        {
            Ok(_) => println!("Successfully uploaded PDF for job {}", job.job_id),
            Err(e) => eprintln!("Failed to upload PDF for job {}: {}", job.job_id, e),
        }
    }

    // Return OK to acknowledge processing of all messages
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    tracing_subscriber::fmt()
        .with_ansi(false)
        .without_time()
        .with_max_level(tracing::Level::INFO)
        .init();

    // Initialize resources properly using the existing Tokio runtime
    let resources = initialize_resources().await;
    RESOURCES.set(resources).expect("Failed to set resources");
    println!("Shared resources initialized");

    run(service_fn(function_handler)).await
}

// Helper function to render PDF using papermake (returns world for caching)
fn render_pdf(
    id: &str,
    template_data: &[u8],
    data: &serde_json::Value,
) -> Result<(papermake::render::RenderResult, Option<TypstWorld>), Box<dyn std::error::Error>> {
    // Initialize papermake renderer
    let template_data = String::from_utf8(template_data.to_vec())?;
    let template = papermake::Template::from_file_content(id, &template_data)?;
    
    // Create world first so we can return it for caching
    let json_data = serde_json::to_string(data)?;
    let mut world = TypstWorld::new(template.content.clone(), json_data);
    
    // Render PDF using our new world
    let result = papermake::render::render_pdf_with_cache(&template, data, Some(&mut world), None)?;
    
    Ok((result, Some(world)))
}

// Helper function to render PDF using an existing cached world
fn render_pdf_with_cache(
    id: &str,
    template_data: &[u8],
    data: &serde_json::Value,
    world: Option<&mut TypstWorld>,
) -> Result<papermake::render::RenderResult, Box<dyn std::error::Error>> {
    // Initialize papermake renderer
    let template_data = String::from_utf8(template_data.to_vec())?;
    let template = papermake::Template::from_file_content(id, &template_data)?;
    
    // Render PDF with the provided world
    let result = papermake::render::render_pdf_with_cache(&template, data, world, None)?;
    
    Ok(result)
}