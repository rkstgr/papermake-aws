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

# SQS queue configuration tuning for high throughput
resource "aws_sqs_queue" "render_queue" {
  name                       = var.queue_name
  visibility_timeout_seconds = max(var.renderer_timeout * 2, 60)  # Longer than Lambda timeout
  message_retention_seconds  = 3600  # 1 hour retention
  receive_wait_time_seconds  = 5     # Enable long polling
  max_message_size           = 262144  # 256 KB
  delay_seconds              = 0      # No delay for immediate processing

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter_queue.arn
    maxReceiveCount     = 3  # Retry failed jobs 3 times
  })

  tags = local.common_tags
}

# Dead letter queue for failed renders
resource "aws_sqs_queue" "dead_letter_queue" {
  name                       = "${var.queue_name}-dlq"
  message_retention_seconds  = 1209600  # 14 days
  
  tags = local.common_tags
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
    }
  }

  tags = local.common_tags
  publish = true
}

# Auto-scaling for the renderer Lambda based on SQS queue metrics
resource "aws_appautoscaling_target" "lambda_target" {
  max_capacity       = 1000  # Maximum number of concurrent Lambda instances
  min_capacity       = 5     # Minimum number of concurrent Lambda instances
  resource_id        = "function:${aws_lambda_function.renderer.function_name}:${aws_lambda_function.renderer.version}"
  scalable_dimension = "lambda:function:ProvisionedConcurrency"
  service_namespace  = "lambda"
}

# Scale up policy - Add more provisioned concurrency when queue depth increases
resource "aws_appautoscaling_policy" "scale_up" {
  name               = "scale-up-${var.environment}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.lambda_target.resource_id
  scalable_dimension = aws_appautoscaling_target.lambda_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.lambda_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "LambdaProvisionedConcurrencyUtilization"
    }
    
    target_value       = 0.75  # Try to keep utilization around 75%
    scale_in_cooldown  = 120   # Wait 2 minutes before scaling in
    scale_out_cooldown = 30    # Only wait 30 seconds before scaling out
  }
}

# SNS topic for scaling alerts
resource "aws_sns_topic" "scaling_alerts" {
  name = "pdf-service-scaling-alerts-${var.environment}"
}

# CloudWatch alarm for SQS queue depth
resource "aws_cloudwatch_metric_alarm" "queue_depth_alarm" {
  alarm_name          = "pdf-queue-depth-alarm-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 100  # Trigger when more than 100 messages are in the queue
  alarm_description   = "This metric monitors SQS queue depth"
  alarm_actions       = [aws_sns_topic.scaling_alerts.arn]
  
  dimensions = {
    QueueName = aws_sqs_queue.render_queue.name
  }
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
  batch_size       = 10
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
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.render_queue.name],
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", aws_sqs_queue.render_queue.name],
            ["AWS/SQS", "NumberOfMessagesReceived", "QueueName", aws_sqs_queue.render_queue.name]
          ]
          view    = "timeSeries"
          stacked = false
          title   = "SQS Queue Metrics"
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
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.renderer.function_name],
            ["AWS/Lambda", "ProvisionedConcurrentExecutions", "FunctionName", aws_lambda_function.renderer.function_name],
            ["AWS/Lambda", "ProvisionedConcurrencyUtilization", "FunctionName", aws_lambda_function.renderer.function_name]
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