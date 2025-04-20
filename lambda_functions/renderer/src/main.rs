use aws_lambda_events::sqs::SqsEvent;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use std::env;
use thiserror::Error;

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

async fn function_handler(event: LambdaEvent<SqsEvent>) -> Result<(), Error> {
    let templates_bucket = env::var("TEMPLATES_BUCKET")
        .map_err(|_| RenderError::EnvVarError("TEMPLATES_BUCKET".to_string()))?;
    let results_bucket = env::var("RESULTS_BUCKET")
        .map_err(|_| RenderError::EnvVarError("RESULTS_BUCKET".to_string()))?;

    // Create S3 client
    let config = aws_config::load_from_env().await;
    let s3_client = aws_sdk_s3::Client::new(&config);

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

        // Get template from S3
        let template_result = s3_client
            .get_object()
            .bucket(&templates_bucket)
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

        let template_data = match template.body.collect().await {
            Ok(data) => data.to_vec(),
            Err(e) => {
                eprintln!("Failed to read template data: {}", e);
                continue;
            }
        };
        
        // Render PDF using papermake
        let render_result = match render_pdf(
            &job.template_id,
            &template_data.as_slice(),
            &job.data,
        ) {
            Ok(result) => result,
            Err(e) => {
                eprintln!("Rendering error: {}", e);
                continue;
            }
        };

        if let None = render_result.pdf {
            eprintln!("Rendering result is None for job {}", job.job_id);
            continue;
        }

        let pdf = render_result.pdf.unwrap();

        // Upload PDF to S3
        match s3_client
            .put_object()
            .bucket(&results_bucket)
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

    run(service_fn(function_handler)).await
}

// Helper function to render PDF using papermake
fn render_pdf(
    id: &str,
    template_data: &[u8],
    data: &serde_json::Value,
) -> Result<papermake::render::RenderResult, Box<dyn std::error::Error>> {
    // Initialize papermake renderer
    let template_data = String::from_utf8(template_data.to_vec())?;
    let template = papermake::Template::from_file_content(id, &template_data)?;
    
    // Render PDF
    let result = papermake::render_pdf(&template, data, None)?;
    
    Ok(result)
}