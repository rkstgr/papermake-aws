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

# SQS Queue
resource "aws_sqs_queue" "render_queue" {
  name                      = var.queue_name
  visibility_timeout_seconds = 900  # 15 minutes
  message_retention_seconds = 1209600  # 14 days
  tags                      = local.common_tags
}

# IAM Roles
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# Lambda Function
resource "aws_lambda_function" "pdf_renderer" {
  filename         = "../../../lambda_functions/pdf_renderer.zip"
  function_name    = "${var.project_name}-pdf-renderer-${var.environment}"
  role            = aws_iam_role.lambda_role.arn
  handler         = "bootstrap"
  architectures   = ["arm64"]
  runtime         = "provided.al2023"
  memory_size     = var.render_lambda_memory
  timeout         = var.render_lambda_timeout
  source_code_hash = filebase64sha256("../../../lambda_functions/pdf_renderer.zip")

  environment {
    variables = {
      TEMPLATES_BUCKET = aws_s3_bucket.templates.id
      RESULTS_BUCKET   = aws_s3_bucket.results.id
      QUEUE_URL        = aws_sqs_queue.render_queue.url
      FONTS_DIR        = "fonts"
    }
  }

  tags = local.common_tags
}

# API Gateway
resource "aws_apigatewayv2_api" "main" {
  name          = var.api_name
  protocol_type = "HTTP"
  description   = "PDF Renderer API"
}

resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = var.api_stage
  auto_deploy = true
}

# API Gateway Integration with Lambda
resource "aws_apigatewayv2_integration" "lambda" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"

  connection_type      = "INTERNET"
  description         = "Lambda integration"
  integration_method  = "POST"
  integration_uri     = aws_lambda_function.pdf_renderer.invoke_arn
}

# API Gateway Route
resource "aws_apigatewayv2_route" "render_pdf" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /render"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pdf_renderer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
} 