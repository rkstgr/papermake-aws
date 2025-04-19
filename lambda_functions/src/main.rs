use aws_lambda_events::apigw::{ApiGatewayProxyRequest, ApiGatewayProxyResponse};
use aws_lambda_events::encodings::Body;
use base64::prelude::BASE64_STANDARD;
use base64::Engine;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::env;
use uuid::Uuid;
use thiserror::Error;

#[derive(Debug, Deserialize)]
struct RenderRequest {
    template_id: String,
    data: serde_json::Value,
}

#[derive(Debug, Serialize, Deserialize)]
struct RenderJob {
    job_id: String,
    template_id: String,
    data: serde_json::Value,
}

#[derive(Error, Debug)]
pub enum RenderError {
    #[error("Failed to parse request: {0}")]
    RequestParseError(String),
    #[error("Failed to render PDF: {0}")]
    RenderingError(String),
    #[error("S3 operation failed: {0}")]
    S3Error(String),
    #[error("SQS operation failed: {0}")]
    SQSError(String),
    #[error("Environment variable not found: {0}")]
    EnvVarError(String),
}

async fn function_handler(event: LambdaEvent<ApiGatewayProxyRequest>) -> Result<ApiGatewayProxyResponse, Error> {

    println!("event: {:?}", event);


    let templates_bucket = env::var("TEMPLATES_BUCKET")
        .map_err(|e| RenderError::EnvVarError("TEMPLATES_BUCKET".to_string()))?;
    let results_bucket = env::var("RESULTS_BUCKET")
        .map_err(|e| RenderError::EnvVarError("RESULTS_BUCKET".to_string()))?;
    let queue_url = env::var("QUEUE_URL")
        .map_err(|e| RenderError::EnvVarError("QUEUE_URL".to_string()))?;

    let body = event.payload.body.unwrap();

    let request: RenderRequest = serde_json::from_str(body.as_str())
        .map_err(|e| RenderError::RequestParseError(e.to_string()))?;
    
    // Generate unique job ID
    let job_id = Uuid::new_v4().to_string();

    // Create S3 and SQS clients
    let config = aws_config::load_from_env().await;
    let s3_client = aws_sdk_s3::Client::new(&config);
    let sqs_client = aws_sdk_sqs::Client::new(&config);

    // Create job message
    let job = RenderJob {
        job_id: job_id.clone(),
        template_id: request.template_id.clone(),
        data: request.data.clone(),
    };

    // Send message to SQS
    sqs_client
        .send_message()
        .queue_url(&queue_url)
        .message_body(serde_json::to_string(&job)?)
        .send()
        .await
        .map_err(|e| RenderError::SQSError(e.to_string()))?;

    // Get template from S3
    let template = s3_client
        .get_object()
        .bucket(&templates_bucket)
        .key(&request.template_id)
        .send()
        .await
        .map_err(|e| RenderError::S3Error(e.to_string()))?;

    let template_data = template.body.collect().await?;
    
    // Render PDF using papermake
    let render_result = match render_pdf(
        &request.template_id,
        &template_data.to_vec().as_slice(),
        &request.data,
    ) {
        Ok(result) => result,
        Err(e) => {
            return Ok(create_error_response(
                500,
                &job_id,
                RenderError::RenderingError(e.to_string()),
            ));
        }
    };

    if let None = render_result.pdf {
        return Ok(create_error_response(
            500,
            &job_id,
            RenderError::RenderingError("Rendering result is None".to_string()),
        ));
    }

    let pdf = render_result.pdf.unwrap();

    // Upload PDF to S3
    s3_client
        .put_object()
        .bucket(&results_bucket)
        .key(format!("{}.pdf", job_id))
        .body(pdf.clone().into())
        .send()
        .await?;

    let pdf_base64 = BASE64_STANDARD.encode(pdf.as_slice());
    
    Ok(ApiGatewayProxyResponse {
        status_code: 200,
        headers: Default::default(),
        body: Some(Body::Text(
            json!({
                "job_id": job_id,
                "status": "completed",
                "pdf_base64": pdf_base64,
                "errors": render_result.errors,
            })
            .to_string(),
        )),
        is_base64_encoded: false,
        multi_value_headers: Default::default(),
    })
}

fn create_error_response(status_code: i32, job_id: &str, error: RenderError) -> ApiGatewayProxyResponse {
    ApiGatewayProxyResponse {
        status_code: status_code as i64,
        headers: Default::default(),
        body: Some(Body::Text(
            json!({
                "job_id": job_id,
                "status": "error",
                "error_type": error.type_name(),
                "error_message": error.to_string(),
            })
            .to_string(),
        )),
        is_base64_encoded: false,
        multi_value_headers: Default::default(),
    }
}

// Helper trait to get the error type name
trait ErrorTypeName {
    fn type_name(&self) -> String;
}

impl ErrorTypeName for RenderError {
    fn type_name(&self) -> String {
        match self {
            RenderError::RequestParseError(_) => "RequestParseError",
            RenderError::RenderingError(_) => "RenderingError",
            RenderError::S3Error(_) => "S3Error",
            RenderError::SQSError(_) => "SQSError",
            RenderError::EnvVarError(_) => "EnvVarError",
        }.to_string()
    }
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