variable "environment" {
  description = "Environment name (e.g., dev, prod)"
  type        = string
}

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "templates_bucket_name" {
  description = "Name of the S3 bucket for storing templates"
  type        = string
}

variable "results_bucket_name" {
  description = "Name of the S3 bucket for storing rendered PDFs"
  type        = string
}

variable "queue_name" {
  description = "Name of the SQS queue for PDF rendering jobs"
  type        = string
}

variable "request_handler_memory" {
  description = "Memory allocation for the request handler Lambda function in MB"
  type        = number
  default     = 128
}

variable "request_handler_timeout" {
  description = "Timeout for the request handler Lambda function in seconds"
  type        = number
  default     = 30
}

variable "renderer_memory" {
  description = "Memory allocation for the renderer Lambda function in MB"
  type        = number
  default     = 1024
}

variable "renderer_timeout" {
  description = "Timeout for the renderer Lambda function in seconds"
  type        = number
  default     = 300
}

variable "api_name" {
  description = "Name of the API Gateway"
  type        = string
}

variable "api_stage" {
  description = "Stage name for the API Gateway"
  type        = string
} 