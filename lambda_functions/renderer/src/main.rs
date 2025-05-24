use aws_lambda_events::sqs::SqsEvent;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use std::env;
use std::sync::Arc;
use std::collections::HashMap;
use tokio::{sync::{RwLock, OnceCell}, time::Instant};
use thiserror::Error;
use papermake::{CachedTemplate, TemplateBuilder};

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
    // Cache compiled templates with their content - much simpler than manual world management
    template_cache: RwLock<HashMap<String, (Vec<u8>, CachedTemplate)>>,
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

        // Get or create cached template
        let cached_template = {
            let cache = resources.template_cache.read().await;
            if let Some((_, cached_template)) = cache.get(&job.template_id) {
                println!("Using cached template for {}", job.template_id);
                cached_template.clone()
            } else {
                drop(cache); // Release read lock before acquiring write lock
                
                println!("Template {} not in cache, fetching from S3", job.template_id);
                
                // Fetch template from S3
                let template_result = resources.s3_client
                    .get_object()
                    .bucket(&resources.templates_bucket)
                    .key(&job.template_id)
                    .send()
                    .await;
                    
                let template_object = match template_result {
                    Ok(t) => t,
                    Err(e) => {
                        eprintln!("Failed to fetch template {}: {}", job.template_id, e);
                        continue;
                    }
                };

                let template_data = match template_object.body.collect().await {
                    Ok(data) => data.to_vec(),
                    Err(e) => {
                        eprintln!("Failed to read template data: {}", e);
                        continue;
                    }
                };
                
                // Parse template content and create cached template directly
                let template_content = match String::from_utf8(template_data.clone()) {
                    Ok(content) => content,
                    Err(e) => {
                        eprintln!("Failed to parse template as UTF-8: {}", e);
                        continue;
                    }
                };
                
                let cached_template = match TemplateBuilder::from_raw_content_cached(&job.template_id, template_content) {
                    Ok(t) => t,
                    Err(e) => {
                        eprintln!("Failed to create cached template: {}", e);
                        continue;
                    }
                };
                
                // Cache both raw data and compiled template
                {
                    let mut cache = resources.template_cache.write().await;
                    cache.insert(job.template_id.clone(), (template_data, cached_template.clone()));
                }
                
                cached_template
            }
        };
        
        // Render PDF - much simpler now!
        let start_time = Instant::now();
        let pdf = match cached_template.render(&job.data) {
            Ok(result) => {
                let render_time = start_time.elapsed();
                println!("Render time: {:?}", render_time);
                result
            },
            Err(e) => {
                eprintln!("Rendering error: {}", e);
                continue;
            }
        };

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