use lambda_runtime::{tracing, Error, LambdaEvent};
use aws_lambda_events::event::sns::SnsEvent;

/// This is the main body for the function.
/// Write your code inside it.
/// There are some code example in the following URLs:
/// - https://github.com/awslabs/aws-lambda-rust-runtime/tree/main/examples
/// - https://github.com/aws-samples/serverless-rust-demo/
pub(crate)async fn function_handler(event: LambdaEvent<SnsEvent>) -> Result<(), Error> {
    // Extract some useful information from the request
    let sns_event = event.payload;
    
    for record in sns_event.records {
        let message = record.sns.message;
        let message_attributes = record.sns.message_attributes;
        println!("Message: {:?}", message);
        println!("Message attributes: {:?}", message_attributes);
    }

    Ok(())
}
