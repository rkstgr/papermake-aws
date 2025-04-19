output "api_endpoint" {
  description = "The endpoint URL of the API Gateway"
  value       = "${aws_apigatewayv2_stage.main.invoke_url}/render"
}

output "templates_bucket_name" {
  description = "Name of the S3 bucket for templates"
  value       = aws_s3_bucket.templates.id
}

output "results_bucket_name" {
  description = "Name of the S3 bucket for rendered PDFs"
  value       = aws_s3_bucket.results.id
}

output "queue_url" {
  description = "URL of the SQS queue"
  value       = aws_sqs_queue.render_queue.url
}

output "lambda_function_name" {
  description = "Name of the PDF render Lambda function"
  value       = aws_lambda_function.render_pdf.function_name
} 