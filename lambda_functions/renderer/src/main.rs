use aws_lambda_events::lambda_function_urls::LambdaFunctionUrlRequest;
use futures;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use opentelemetry::{global, trace::TracerProvider, KeyValue};
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{trace::SdkTracerProvider, Resource};
use papermake::{CachedTemplate, TemplateBuilder, TemplateId};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::env;
use std::sync::Arc;
use thiserror::Error;
use tokio::{
    sync::{OnceCell, RwLock},
    time::Instant,
};
use tracing::{error, info, instrument, Span};
use tracing_subscriber::{layer::SubscriberExt, Registry};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
struct RenderRequest {
    jobs: Vec<RenderJobRequest>,
}

#[derive(Debug, Deserialize)]
struct RenderJobRequest {
    template_id: String,
    data: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct JobResult {
    job_id: String,
    template_id: String,
    status: String,
    s3_key: Option<String>,
    file_size: Option<u64>,
    error: Option<String>,
}

#[derive(Debug, Serialize)]
struct BatchResponse {
    results: Vec<JobResult>,
    summary: BatchSummary,
}

#[derive(Debug, Serialize)]
struct BatchSummary {
    total: usize,
    success: usize,
    failed: usize,
}

#[derive(Error, Debug)]
pub enum RenderError {
    #[error("Failed to parse job: {0}")]
    JobParseError(String),
    #[error("Failed to render PDF: {0}")]
    RenderingError(String),
    #[error("S3 operation failed: {0}")]
    S3Error(String),
    #[error("Environment variable not found: {0}")]
    EnvVarError(String),
}

// Shared resources across invocations
#[derive(Debug)]
struct SharedResources {
    s3_client: aws_sdk_s3::Client,
    templates_bucket: String,
    results_bucket: String,
    // Cache compiled templates with their content - much simpler than manual world management
    template_cache: RwLock<HashMap<String, (Vec<u8>, CachedTemplate)>>,
}

// Use OnceCell instead of Lazy to initialize asynchronously
static RESOURCES: OnceCell<Arc<SharedResources>> = OnceCell::const_new();

// Render PDF without uploading to S3
async fn render_pdf(
    resources: &SharedResources,
    job_id: &str,
    job_request: &RenderJobRequest,
) -> Result<(String, Vec<u8>), RenderError> {
    // Get or create cached template
    let cached_template = get_cached_template(resources, &job_request.template_id).await?;

    // Render PDF
    let render_span = tracing::info_span!("pdf_render");
    let start_time = Instant::now();
    let render_result = {
        let _enter = render_span.enter();
        cached_template.render(&job_request.data)
    };

    let pdf_data = match render_result {
        Ok(result) => {
            let render_time = start_time.elapsed();
            info!("Render time: {:?}", render_time);
            match result.pdf {
                Some(pdf) => pdf,
                None => {
                    return Err(RenderError::RenderingError(
                        "Render result is empty".to_string(),
                    ))
                }
            }
        }
        Err(e) => return Err(RenderError::RenderingError(e.to_string())),
    };

    let s3_key = format!("{}.pdf", job_id);
    Ok((s3_key, pdf_data))
}

// Upload PDF to S3
async fn upload_pdf_to_s3(
    resources: &SharedResources,
    job_id: &str,
    s3_key: &str,
    pdf_data: Vec<u8>,
) -> Result<u64, RenderError> {
    let upload_span = tracing::info_span!("s3_pdf_upload", job_id = %job_id);
    let file_size = pdf_data.len() as u64;

    {
        let _enter = upload_span.enter();
        resources
            .s3_client
            .put_object()
            .bucket(&resources.results_bucket)
            .key(s3_key)
            .body(pdf_data.into())
            .send()
            .await
            .map_err(|e| RenderError::S3Error(format!("Failed to upload PDF: {}", e)))?;
    }

    info!("Successfully uploaded PDF for job {}", job_id);
    Ok(file_size)
}

// Get cached template or fetch from S3
async fn get_cached_template(
    resources: &SharedResources,
    template_id: &str,
) -> Result<CachedTemplate, RenderError> {
    let cache_span = tracing::info_span!("template_cache_lookup");
    let _enter = cache_span.enter();

    let cache = resources.template_cache.read().await;
    if let Some((_, cached_template)) = cache.get(template_id) {
        info!("Using cached template for {}", template_id);
        Span::current().record("cache_hit", true);
        return Ok(cached_template.clone());
    }
    drop(cache);

    Span::current().record("cache_hit", false);
    info!("Template {} not in cache, fetching from S3", template_id);

    // Fetch template from S3
    let s3_fetch_span = tracing::info_span!("s3_template_fetch");
    let s3_start = Instant::now();
    let template_result = {
        let _enter = s3_fetch_span.enter();
        resources
            .s3_client
            .get_object()
            .bucket(&resources.templates_bucket)
            .key(template_id)
            .send()
            .await
    };
    let s3_fetch_time = s3_start.elapsed();
    info!("S3 fetch time: {:?}", s3_fetch_time);

    let template_object = template_result
        .map_err(|e| RenderError::S3Error(format!("Failed to fetch template: {}", e)))?;

    let template_data = template_object
        .body
        .collect()
        .await
        .map_err(|e| RenderError::S3Error(format!("Failed to read template data: {}", e)))?
        .to_vec();

    // Parse template content and create cached template
    let compile_span = tracing::info_span!("template_compile");
    let compile_start = Instant::now();

    let template_content = String::from_utf8(template_data.clone()).map_err(|e| {
        RenderError::RenderingError(format!("Failed to parse template as UTF-8: {}", e))
    })?;

    let cached_template = {
        let _enter = compile_span.enter();
        TemplateBuilder::from_raw_content_cached(
            TemplateId::from(template_id.to_string()),
            template_content,
        )
        .map_err(|e| {
            RenderError::RenderingError(format!("Failed to create cached template: {}", e))
        })?
    };
    let compile_time = compile_start.elapsed();
    info!("Template compile time: {:?}", compile_time);

    // Cache both raw data and compiled template
    {
        let mut cache = resources.template_cache.write().await;
        cache.insert(
            template_id.to_string(),
            (template_data, cached_template.clone()),
        );
    }

    Ok(cached_template)
}

// Initialize resources asynchronously
async fn initialize_resources() -> Arc<SharedResources> {
    // Read environment variables
    let templates_bucket =
        env::var("TEMPLATES_BUCKET").expect("TEMPLATES_BUCKET environment variable not set");
    let results_bucket =
        env::var("RESULTS_BUCKET").expect("RESULTS_BUCKET environment variable not set");

    // Initialize AWS client
    let config = aws_config::load_from_env().await;
    let s3_client = aws_sdk_s3::Client::new(&config);

    // Create and return resources
    Arc::new(SharedResources {
        s3_client,
        templates_bucket,
        results_bucket,
        template_cache: RwLock::new(HashMap::new()),
    })
}

#[instrument(skip(event), fields(batch_size))]
async fn function_handler(event: LambdaEvent<LambdaFunctionUrlRequest>) -> Result<Value, Error> {
    // Parse request body
    let body = event
        .payload
        .body
        .ok_or_else(|| Error::from("Missing request body"))?;
    let request: RenderRequest = serde_json::from_str(&body).map_err(|e| {
        error!("Error parsing request body: {}", e);
        Error::from(format!("Invalid request format: {}", e))
    })?;

    // Get the shared resources
    let resources = RESOURCES.get().expect("Resources not initialized");

    info!("Processing batch of {} jobs", request.jobs.len());
    Span::current().record("batch_size", request.jobs.len());

    // Step 1: Render all PDFs sequentially (maintains proper tracing)
    let render_span = tracing::info_span!("render_phase");
    let mut rendered_jobs = Vec::new();
    let mut failed_jobs = Vec::new();

    {
        let _enter = render_span.enter();
        for job_request in request.jobs {
            let job_id = Uuid::new_v4().to_string();

            let job_span = tracing::info_span!(
                "render_job",
                job_id = %job_id,
                template_id = %job_request.template_id
            );
            let _enter = job_span.enter();

            info!(
                "Rendering job {}: template={}",
                job_id, job_request.template_id
            );

            match render_pdf(&resources, &job_id, &job_request).await {
                Ok((s3_key, pdf_data)) => {
                    rendered_jobs.push((job_id, job_request.template_id.clone(), s3_key, pdf_data));
                }
                Err(e) => {
                    error!("Job {} rendering failed: {}", job_id, e);
                    failed_jobs.push(JobResult {
                        job_id: job_id.clone(),
                        template_id: job_request.template_id.clone(),
                        status: "error".to_string(),
                        s3_key: None,
                        file_size: None,
                        error: Some(e.to_string()),
                    });
                }
            }
        }
    }

    // Step 2: Upload all PDFs in parallel
    let upload_span = tracing::info_span!("upload_phase", upload_count = rendered_jobs.len());
    let mut upload_tasks = Vec::new();
    let _enter = upload_span.enter();
    {
        for (job_id, template_id, s3_key, pdf_data) in rendered_jobs {
            let resources = Arc::clone(&resources);
            let task = tokio::spawn(async move {
                match upload_pdf_to_s3(&resources, &job_id, &s3_key, pdf_data).await {
                    Ok(file_size) => JobResult {
                        job_id: job_id.clone(),
                        template_id,
                        status: "success".to_string(),
                        s3_key: Some(s3_key),
                        file_size: Some(file_size),
                        error: None,
                    },
                    Err(e) => {
                        error!("Job {} upload failed: {}", job_id, e);
                        JobResult {
                            job_id: job_id.clone(),
                            template_id,
                            status: "error".to_string(),
                            s3_key: None,
                            file_size: None,
                            error: Some(e.to_string()),
                        }
                    }
                }
            });
            upload_tasks.push(task);
        }
    }

    // Wait for all uploads to complete
    let upload_results = futures::future::join_all(upload_tasks).await;
    drop(_enter);

    let failed_count_initial = failed_jobs.len();
    let mut results = failed_jobs;
    let mut success_count = 0;
    let mut failed_count = failed_count_initial;

    for result in upload_results {
        match result {
            Ok(job_result) => {
                if job_result.status == "success" {
                    success_count += 1;
                } else {
                    failed_count += 1;
                }
                results.push(job_result);
            }
            Err(e) => {
                failed_count += 1;
                error!("Upload task panicked: {}", e);
            }
        }
    }

    // Create response
    let response = BatchResponse {
        results,
        summary: BatchSummary {
            total: success_count + failed_count,
            success: success_count,
            failed: failed_count,
        },
    };

    info!(
        "Batch processing complete: {} total, {} success, {} failed",
        response.summary.total, response.summary.success, response.summary.failed
    );

    Ok(json!(response))
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    // Initialize OpenTelemetry exporter
    let otlp_endpoint =
        env::var("OTLP_ENDPOINT").expect("OTLP_ENDPOINT environment variable not set");

    let exporter = opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_endpoint(otlp_endpoint)
        .build()
        .expect("Failed to create OTLP exporter");

    // Create resource with service information
    let resource = Resource::builder()
        .with_service_name("pdf-renderer-lambda")
        .with_attribute(KeyValue::new("service.version", "0.1.0"))
        .build();

    // Create tracer provider
    let tracer_provider = SdkTracerProvider::builder()
        .with_simple_exporter(exporter)
        .with_resource(resource)
        .build();

    // Get tracer
    let tracer = tracer_provider.tracer("pdf-renderer-lambda");

    // Set global tracer provider
    global::set_tracer_provider(tracer_provider.clone());

    // Initialize tracing subscriber with OpenTelemetry layer
    let telemetry = tracing_opentelemetry::layer().with_tracer(tracer);

    let subscriber = Registry::default()
        .with(
            tracing_subscriber::fmt::layer()
                .with_ansi(false)
                .without_time(),
        )
        .with(tracing_subscriber::filter::LevelFilter::INFO)
        .with(telemetry);

    tracing::subscriber::set_global_default(subscriber).expect("Failed to set subscriber");

    // Initialize resources properly using the existing Tokio runtime
    let resources = initialize_resources().await;
    RESOURCES.set(resources).expect("Failed to set resources");
    info!("Shared resources initialized");

    let result = run(service_fn(function_handler)).await;

    // Shutdown the tracer to ensure all spans are exported
    if let Err(e) = tracer_provider.shutdown() {
        eprintln!("Error shutting down tracer provider: {:?}", e);
    }

    result
}
