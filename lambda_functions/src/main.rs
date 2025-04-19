use aws_lambda_events::apigw::{ApiGatewayV2httpRequest, ApiGatewayV2httpResponse};
use aws_lambda_events::encodings::Body;
use base64::prelude::BASE64_STANDARD;
use base64::Engine;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::env;
use uuid::Uuid;

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

async fn function_handler(event: LambdaEvent<Value>) -> Result<ApiGatewayV2httpResponse, Error> {

    println!("event: {:?}", event);

    let templates_bucket = env::var("TEMPLATES_BUCKET")?;
    let results_bucket = env::var("RESULTS_BUCKET")?;
    let queue_url = env::var("QUEUE_URL")?;

    // Parse request body
    let request: RenderRequest = serde_json::from_str(event.payload.as_str().ok_or("Missing payload")?)?;
    
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
        .await?;

    // Get template from S3
    let template = s3_client
        .get_object()
        .bucket(&templates_bucket)
        .key(&request.template_id)
        .send()
        .await?;

    let template_data = template.body.collect().await?;
    
    // Render PDF using papermake
    let render_result = match render_pdf(
        &request.template_id,
        &template_data.to_vec().as_slice(),
        &request.data,
    ) {
        Ok(result) => result,
        Err(e) => {
            return Ok(ApiGatewayV2httpResponse {
                status_code: 500,
                headers: Default::default(),
                body: Some(Body::Text(
                    json!({
                        "job_id": job_id,
                        "status": "error",
                        "errors": vec![e.to_string()],
                    })
                    .to_string(),
                )),
                is_base64_encoded: false,
                cookies: Default::default(),
                multi_value_headers: Default::default(),
            });
        }
    };

    if let None = render_result.pdf {
        return Ok(ApiGatewayV2httpResponse {
            status_code: 500,
            headers: Default::default(),
            body: Some(Body::Text(
                json!({
                    "job_id": job_id,
                    "status": "error", 
                    "errors": render_result.errors,
                })
                .to_string(),
            )),
            is_base64_encoded: false,
            cookies: Default::default(),
            multi_value_headers: Default::default(),
        });
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
    
    Ok(ApiGatewayV2httpResponse {
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
        cookies: Default::default(),
        multi_value_headers: Default::default(),
    })
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