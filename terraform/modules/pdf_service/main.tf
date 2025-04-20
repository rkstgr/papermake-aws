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
  name                       = var.queue_name
  visibility_timeout_seconds = 900  # 15 minutes
  message_retention_seconds  = 1209600  # 14 days
  tags                       = local.common_tags
}

# Request Handler Lambda Function
resource "aws_lambda_function" "request_handler" {
  filename         = "../../../lambda_functions/request_handler/pdf_request_handler.zip"
  function_name    = "${var.project_name}-request-handler-${var.environment}"
  role             = aws_iam_role.request_handler_role.arn
  handler          = "bootstrap"
  architectures    = ["arm64"]
  runtime          = "provided.al2023"
  memory_size      = var.request_handler_memory
  timeout          = var.request_handler_timeout
  source_code_hash = filebase64sha256("../../../lambda_functions/request_handler/pdf_request_handler.zip")

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.render_queue.url
    }
  }

  tags = local.common_tags
}

# Renderer Lambda Function
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

# API Gateway Integration with Request Handler Lambda
resource "aws_apigatewayv2_integration" "request_handler" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"

  connection_type     = "INTERNET"
  description         = "Request Handler Lambda integration"
  integration_method  = "POST"
  integration_uri     = aws_lambda_function.request_handler.invoke_arn
}

# API Gateway Route
resource "aws_apigatewayv2_route" "render_pdf" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /render"
  target    = "integrations/${aws_apigatewayv2_integration.request_handler.id}"
}

# Request Handler Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.request_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# Lambda Event Source Mapping for Renderer
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.render_queue.arn
  function_name    = aws_lambda_function.renderer.arn
  batch_size       = 1
} 