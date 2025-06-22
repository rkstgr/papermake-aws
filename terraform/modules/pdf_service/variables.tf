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


variable "otlp_endpoint" {
  description = "OpenTelemetry OTLP endpoint for tracing"
  type        = string
} 