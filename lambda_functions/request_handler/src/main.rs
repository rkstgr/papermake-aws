use aws_lambda_events::{apigw::{ApiGatewayProxyRequest, ApiGatewayProxyResponse}, encodings::Body};
use serde::{Deserialize, Serialize};
use serde_json::json;
use uuid::Uuid;
use lambda_runtime::{service_fn, LambdaEvent, Error, run};

#[derive(Deserialize)]
struct RenderRequest {
    template_id: String,
    data: serde_json::Value,
}

#[derive(Serialize)]
struct RenderJob {
    job_id: String,
    template_id: String,
    data: serde_json::Value,
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

async fn function_handler(event: LambdaEvent<ApiGatewayProxyRequest>) -> Result<ApiGatewayProxyResponse, Error> {
    // Parse request
    let body = event.payload.body.unwrap();
    let request: RenderRequest = serde_json::from_str(body.as_str())?;

    let queue_url = std::env::var("QUEUE_URL").expect("QUEUE_URL must be set");
    
    // Generate job ID
    let job_id = Uuid::new_v4().to_string();
    
    // Create job and send to SQS
    let job = RenderJob {
        job_id: job_id.clone(),
        template_id: request.template_id.clone(),
        data: request.data.clone(),
    };

    let config = aws_config::load_from_env().await;
    let sqs_client = aws_sdk_sqs::Client::new(&config);
    
    // Send to SQS and return immediately
    sqs_client.send_message()
        .queue_url(&queue_url)
        .message_body(serde_json::to_string(&job)?)
        .send()
        .await?;
    
    // Return job ID immediately
    Ok(ApiGatewayProxyResponse {
        status_code: 202, // Accepted
        body: Some(Body::Text(json!({"job_id": job_id, "status": "queued"}).to_string())),
        is_base64_encoded: false,
        ..Default::default()
    })
}