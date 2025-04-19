use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use lambda_http::{service_fn, tracing, Error, LambdaEvent, Request, Response, Body};
struct SQSManager {
    client: aws_sdk_sqs::Client,
    queue_url: String,
}

impl SQSManager {
    fn new(client: aws_sdk_sqs::Client, queue_url: String) -> Self {
        Self { client, queue_url }
    }
}
#[tokio::main]
async fn main() -> Result<(), Error> {
    tracing::init_default_subscriber();

    // read the queue url from the environment
    let queue_url = std::env::var("QUEUE_URL").expect("could not read QUEUE_URL");
    // build the config from environment variables (fed by AWS Lambda)
    let config = aws_config::from_env().load().await;
    // create our SQS Manager
    let sqs_manager = SQSManager::new(aws_sdk_sqs::Client::new(&config), queue_url);
    let sqs_manager_ref = &sqs_manager;

    // no need to create a SQS Client for each incoming request, let's use a shared state
    let handler_func_closure = |event: LambdaEvent<Value>| async move { process_event(event, sqs_manager_ref).await };
    lambda_runtime::run(service_fn(handler_func_closure)).await?;
    Ok(())
}


#[derive(Debug, Serialize, Deserialize)]
struct RenderingMessage {
    template_id: String,
    data: Value,
}

async fn process_event(event: LambdaEvent<Value>, sqs_manager: &SQSManager) -> Result<(), Error> {
    
    let rendering_message: RenderingMessage = serde_json::from_value(event.payload)?;

    // send our message to SQS
    sqs_manager
        .client
        .send_message()
        .queue_url(&sqs_manager.queue_url)
        .message_body(json!(rendering_message).to_string())
        .send()
        .await?;

    Ok(())
}