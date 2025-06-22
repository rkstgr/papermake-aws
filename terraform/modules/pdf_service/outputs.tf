output "function_url" {
  description = "The HTTPS URL of the Lambda function"
  value       = aws_lambda_function_url.renderer.function_url
}

output "templates_bucket" {
  description = "The name of the templates S3 bucket"
  value       = aws_s3_bucket.templates.id
}

output "results_bucket" {
  description = "The name of the results S3 bucket"
  value       = aws_s3_bucket.results.id
}


output "renderer_function_name" {
  description = "The name of the renderer Lambda function"
  value       = aws_lambda_function.renderer.function_name
}
