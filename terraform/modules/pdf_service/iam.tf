
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


# Attach policies to Renderer role
resource "aws_iam_role_policy_attachment" "renderer_logs" {
  role       = aws_iam_role.renderer_role.name
  policy_arn = aws_iam_policy.renderer_logs.arn
}


resource "aws_iam_role_policy_attachment" "renderer_s3" {
  role       = aws_iam_role.renderer_role.name
  policy_arn = aws_iam_policy.renderer_s3.arn
} 