locals {
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
  }
}

# S3 Buckets
resource "aws_s3_bucket" "templates" {
  bucket = var.templates_bucket_name
  tags   = local.common_tags
}

resource "aws_s3_bucket" "results" {
  bucket = var.results_bucket_name
  tags   = local.common_tags
}

# Current region data source
data "aws_region" "current" {}



# PDF Renderer Lambda Function
resource "aws_lambda_function" "renderer" {
  filename         = "../../../lambda_functions/renderer/pdf_renderer.zip"
  function_name    = "${var.project_name}-renderer-${var.environment}"
  role             = aws_iam_role.renderer_role.arn
  handler          = "bootstrap"
  architectures    = ["arm64"]
  runtime          = "provided.al2023"
  memory_size      = var.renderer_memory
  timeout          = var.renderer_timeout
  source_code_hash = filebase64sha256("../../../lambda_functions/renderer/pdf_renderer.zip")

  environment {
    variables = {
      TEMPLATES_BUCKET = aws_s3_bucket.templates.id
      RESULTS_BUCKET   = aws_s3_bucket.results.id
      FONTS_DIR        = "fonts"
      OTLP_ENDPOINT    = var.otlp_endpoint
    }
  }

  tags = local.common_tags
}


# SNS topic for scaling alerts
resource "aws_sns_topic" "scaling_alerts" {
  name = "pdf-service-scaling-alerts-${var.environment}"
}


# Lambda Function URL for Renderer
resource "aws_lambda_function_url" "renderer" {
  function_name      = aws_lambda_function.renderer.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_methods     = ["POST"]
    allow_origins     = ["*"]
    expose_headers    = ["keep-alive", "date"]
    max_age          = 86400
  }
}


# Create a CloudWatch Dashboard for monitoring
resource "aws_cloudwatch_dashboard" "pdf_service" {
  dashboard_name = "pdf-service-dashboard-${var.environment}"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.renderer.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.renderer.function_name]
          ]
          view    = "timeSeries"
          stacked = false
          title   = "Lambda Invocations & Errors"
          region  = data.aws_region.current.name
          period  = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.renderer.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.renderer.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.renderer.function_name]
          ]
          view    = "timeSeries"
          stacked = false
          title   = "Lambda Renderer Metrics"
          region  = data.aws_region.current.name
          period  = 60
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.renderer.function_name, {"stat": "Average"}],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.renderer.function_name, {"stat": "Maximum"}]
          ]
          view    = "timeSeries"
          stacked = false
          title   = "Lambda Duration"
          region  = data.aws_region.current.name
          period  = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.renderer.function_name]
          ]
          view    = "timeSeries"
          stacked = false
          title   = "Lambda Concurrency"
          region  = data.aws_region.current.name
          period  = 60
        }
      }
    ]
  })
} 