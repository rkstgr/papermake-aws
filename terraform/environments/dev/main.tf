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

# Outputs
output "function_url" {
  description = "The HTTPS URL of the PDF renderer Lambda function"
  value       = module.pdf_service.function_url
}

output "templates_bucket" {
  description = "Name of the S3 bucket for templates"
  value       = module.pdf_service.templates_bucket
}

output "results_bucket" {
  description = "Name of the S3 bucket for results"
  value       = module.pdf_service.results_bucket
}

output "renderer_function_name" {
  description = "Name of the renderer Lambda function"
  value       = module.pdf_service.renderer_function_name
} 