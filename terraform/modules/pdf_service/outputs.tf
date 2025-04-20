output "api_endpoint" {
  description = "The URL of the API Gateway endpoint"
  value       = "${aws_apigatewayv2_stage.main.invoke_url}"
}

output "render_route" {
  description = "The route path for rendering PDFs"
  value       = "POST /render"
}

output "templates_bucket" {
  description = "The name of the templates S3 bucket"
  value       = aws_s3_bucket.templates.id
}

output "results_bucket" {
  description = "The name of the results S3 bucket"
  value       = aws_s3_bucket.results.id
}

output "queue_url" {
  description = "The URL of the SQS queue"
  value       = aws_sqs_queue.render_queue.url
}

output "request_handler_function_name" {
  description = "The name of the request handler Lambda function"
  value       = aws_lambda_function.request_handler.function_name
}

output "renderer_function_name" {
  description = "The name of the renderer Lambda function"
  value       = aws_lambda_function.renderer.function_name
} 