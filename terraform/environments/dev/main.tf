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

module "pdf_service" {
  source = "../../modules/pdf_service"

  environment = "dev"
  project_name = "papermake-pdf"

  # S3 bucket configurations
  templates_bucket_name = "papermake-templates-dev"
  results_bucket_name = "papermake-results-dev"

  # SQS queue configuration
  queue_name = "pdf-render-queue-dev"

  # Lambda configurations
  request_handler_memory = 128
  request_handler_timeout = 30  # 30 seconds
  
  renderer_memory = 256 # can be increased to 1024 for longer documents
  renderer_timeout = 300  # 5 minutes

  # API Gateway configuration
  api_name = "pdf-renderer-api-dev"
  api_stage = "v1"
} 