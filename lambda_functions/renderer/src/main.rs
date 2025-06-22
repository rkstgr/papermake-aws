use aws_lambda_events::sqs::SqsEvent;
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use opentelemetry::{global, trace::TracerProvider, KeyValue};
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{trace::SdkTracerProvider, Resource};
use papermake::{CachedTemplate, TemplateBuilder, TemplateId};
use serde::{Deserialize, Serialize};
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

#[derive(Debug, Deserialize, Serialize)]
struct RenderJob {
    job_id: String,
    template_id: String,
    data: serde_json::Value,
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

#[instrument(skip(event), fields(batch_size = event.payload.records.len()))]
async fn function_handler(event: LambdaEvent<SqsEvent>) -> Result<(), Error> {
    // Get the shared resources
    let resources = RESOURCES.get().expect("Resources not initialized");

    info!("Batch size: {}", event.payload.records.len());

    // Process each message from SQS
    for record in event.payload.records {
        let message_body = record
            .body
            .as_ref()
            .ok_or_else(|| RenderError::JobParseError("Empty message body".to_string()))?;

        // Parse the job from the message
        let job: RenderJob = match serde_json::from_str(message_body) {
            Ok(job) => job,
            Err(e) => {
                eprintln!("Failed to parse job: {}", e);
                continue; // Skip this message and move to the next one
            }
        };

        let job_span = tracing::info_span!(
            "process_job",
            job_id = %job.job_id,
            template_id = %job.template_id
        );
        let _enter = job_span.enter();

        info!(
            "Processing job {}: template={}",
            job.job_id, job.template_id
        );

        // Get or create cached template
        let cached_template = {
            let cache_span = tracing::info_span!("template_cache_lookup");
            let _enter = cache_span.enter();

            let cache = resources.template_cache.read().await;
            if let Some((_, cached_template)) = cache.get(&job.template_id) {
                info!("Using cached template for {}", job.template_id);
                Span::current().record("cache_hit", true);
                cached_template.clone()
            } else {
                drop(cache); // Release read lock before acquiring write lock
                Span::current().record("cache_hit", false);

                info!(
                    "Template {} not in cache, fetching from S3",
                    job.template_id
                );

                // Fetch template from S3
                let s3_fetch_span = tracing::info_span!("s3_template_fetch");
                let s3_start = Instant::now();
                let template_result = {
                    let _enter = s3_fetch_span.enter();
                    resources
                        .s3_client
                        .get_object()
                        .bucket(&resources.templates_bucket)
                        .key(&job.template_id)
                        .send()
                        .await
                };
                let s3_fetch_time = s3_start.elapsed();
                info!("S3 fetch time: {:?}", s3_fetch_time);

                let template_object = match template_result {
                    Ok(t) => t,
                    Err(e) => {
                        error!("Failed to fetch template {}: {}", job.template_id, e);
                        continue;
                    }
                };

                let template_data = match template_object.body.collect().await {
                    Ok(data) => data.to_vec(),
                    Err(e) => {
                        error!("Failed to read template data: {}", e);
                        continue;
                    }
                };

                // Parse template content and create cached template directly
                let compile_span = tracing::info_span!("template_compile");
                let compile_start = Instant::now();

                let template_content = match String::from_utf8(template_data.clone()) {
                    Ok(content) => content,
                    Err(e) => {
                        error!("Failed to parse template as UTF-8: {}", e);
                        continue;
                    }
                };

                let cached_template = {
                    let _enter = compile_span.enter();
                    match TemplateBuilder::from_raw_content_cached(
                        TemplateId::from(job.template_id.clone()),
                        template_content,
                    ) {
                        Ok(t) => t,
                        Err(e) => {
                            error!("Failed to create cached template: {}", e);
                            continue;
                        }
                    }
                };
                let compile_time = compile_start.elapsed();
                info!("Template compile time: {:?}", compile_time);

                // Cache both raw data and compiled template
                {
                    let mut cache = resources.template_cache.write().await;
                    cache.insert(
                        job.template_id.clone(),
                        (template_data, cached_template.clone()),
                    );
                }

                cached_template
            }
        };

        // Render PDF - much simpler now!
        let render_span = tracing::info_span!("pdf_render");
        let start_time = Instant::now();
        let render_result = {
            let _enter = render_span.enter();
            match cached_template.render(&job.data) {
                Ok(result) => {
                    let render_time = start_time.elapsed();
                    info!("Render time: {:?}", render_time);
                    result
                }
                Err(e) => {
                    error!("Rendering error: {}", e);
                    continue;
                }
            }
        };

        let Some(pdf) = render_result.pdf else {
            error!("Render result is empty");
            continue;
        };

        // Upload PDF to S3
        let upload_span = tracing::info_span!("s3_pdf_upload");
        let _ = {
            let _enter = upload_span.enter();
            resources
                .s3_client
                .put_object()
                .bucket(&resources.results_bucket)
                .key(format!("{}.pdf", job.job_id))
                .body(pdf.into())
                .send()
                .await
        };

        info!("Successfully uploaded PDF for job {}", job.job_id);
    }

    // Return OK to acknowledge processing of all messages
    Ok(())
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
