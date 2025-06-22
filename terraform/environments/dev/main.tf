terraform {
  required_version = ">= 1.0.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # These will be provided via backend config
  }
}

provider "aws" {
  region = "eu-central-1"  # Updated to match S3 bucket region
}

variable "otlp_endpoint" {
  description = "OpenTelemetry OTLP endpoint for tracing"
  type        = string
}

module "pdf_service" {
  source = "../../modules/pdf_service"

  environment = "dev"
  project_name = "papermake-pdf"

  # S3 bucket configurations
  templates_bucket_name = "papermake-templates-dev"
  results_bucket_name = "papermake-results-dev"

  # Lambda configurations
  
  renderer_memory = 512 # increased for batch processing
  renderer_timeout = 900  # 15 minutes for larger batches

  
  # OpenTelemetry configuration
  otlp_endpoint = var.otlp_endpoint
} 