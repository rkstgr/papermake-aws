use aws_lambda_events::{apigw::{ApiGatewayProxyRequest, ApiGatewayProxyResponse}, encodings::Body};
use serde::{Deserialize, Serialize};
use serde_json::json;
use uuid::Uuid;
use lambda_runtime::{service_fn, LambdaEvent, Error, run};

#[derive(Deserialize)]
struct RenderRequest {
    jobs: Vec<RenderJobRequest>,
}

#[derive(Deserialize)]
struct RenderJobRequest {
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
    let body = event.payload.body.ok_or_else(|| Error::from("Missing request body"))?;
    let request: RenderRequest = serde_json::from_str(&body).map_err(|e| {
        eprintln!("Error parsing request body: {}", e);
        Error::from(format!("Invalid request format: {}", e))
    })?;

    let queue_url = std::env::var("QUEUE_URL").expect("QUEUE_URL must be set");

    let config = aws_config::load_from_env().await;
    let sqs_client = aws_sdk_sqs::Client::new(&config);
    
    let mut job_ids = Vec::new();
    // Create job and send to SQS
    for job in request.jobs {
        let job_id = Uuid::new_v4().to_string();

        let job = RenderJob {
            job_id: job_id.clone(),
            template_id: job.template_id.clone(),
            data: job.data.clone(),
        };

        // Send to SQS and return immediately
        sqs_client.send_message()
        .queue_url(&queue_url)
        .message_body(serde_json::to_string(&job)?)
        .send()
        .await?;

        job_ids.push(job_id);
    }
    
    // Return job ID immediately
    Ok(ApiGatewayProxyResponse {
        status_code: 202, // Accepted
        body: Some(Body::Text(json!({"job_ids": job_ids, "status": "queued"}).to_string())),
        is_base64_encoded: false,
        ..Default::default()
    })
}