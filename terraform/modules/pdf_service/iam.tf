# IAM Role for Request Handler Lambda
resource "aws_iam_role" "request_handler_role" {
  name = "${var.project_name}-request-handler-role-${var.environment}"

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

# IAM Role for Renderer Lambda
resource "aws_iam_role" "renderer_role" {
  name = "${var.project_name}-renderer-role-${var.environment}"

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

# Request Handler - CloudWatch Logs permissions
resource "aws_iam_policy" "request_handler_logs" {
  name        = "${var.project_name}-request-handler-logs-${var.environment}"
  description = "IAM policy for logging from request handler lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Renderer - CloudWatch Logs permissions
resource "aws_iam_policy" "renderer_logs" {
  name        = "${var.project_name}-renderer-logs-${var.environment}"
  description = "IAM policy for logging from renderer lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Request Handler - SQS permissions
resource "aws_iam_policy" "request_handler_sqs" {
  name        = "${var.project_name}-request-handler-sqs-${var.environment}"
  description = "IAM policy for SQS access from request handler lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:SendMessage"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.render_queue.arn
      }
    ]
  })
}

# Renderer - SQS permissions
resource "aws_iam_policy" "renderer_sqs" {
  name        = "${var.project_name}-renderer-sqs-${var.environment}"
  description = "IAM policy for SQS access from renderer lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Effect   = "Allow"
        Resource = aws_sqs_queue.render_queue.arn
      }
    ]
  })
}

# Renderer - S3 permissions
resource "aws_iam_policy" "renderer_s3" {
  name        = "${var.project_name}-renderer-s3-${var.environment}"
  description = "IAM policy for S3 access from renderer lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject"
        ]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.templates.arn}/*"
      },
      {
        Action = [
          "s3:PutObject"
        ]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.results.arn}/*"
      }
    ]
  })
}

# Attach policies to Request Handler role
resource "aws_iam_role_policy_attachment" "request_handler_logs" {
  role       = aws_iam_role.request_handler_role.name
  policy_arn = aws_iam_policy.request_handler_logs.arn
}

resource "aws_iam_role_policy_attachment" "request_handler_sqs" {
  role       = aws_iam_role.request_handler_role.name
  policy_arn = aws_iam_policy.request_handler_sqs.arn
}

# Attach policies to Renderer role
resource "aws_iam_role_policy_attachment" "renderer_logs" {
  role       = aws_iam_role.renderer_role.name
  policy_arn = aws_iam_policy.renderer_logs.arn
}

resource "aws_iam_role_policy_attachment" "renderer_sqs" {
  role       = aws_iam_role.renderer_role.name
  policy_arn = aws_iam_policy.renderer_sqs.arn
}

resource "aws_iam_role_policy_attachment" "renderer_s3" {
  role       = aws_iam_role.renderer_role.name
  policy_arn = aws_iam_policy.renderer_s3.arn
} 