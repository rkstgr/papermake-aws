# Local

Run the lambda function locally (requires [cargo-lambda](https://www.cargo-lambda.info/))

```sh
cd lambda_functions/renderer
TEMPLATES_BUCKET=<bucket> RESULTS_BUCKET=<bucket> cargo lambda watch
```

and in another terminal, invoke it with a Lambda function URL event whose `body`
is a render request:

```sh
cargo lambda invoke --data-file request.json --output-format json
```

where the `body` field of `request.json` contains e.g.
`{"jobs": [{"template_id": "invoice.typ", "data": {}}]}`.

Setting `OTLP_ENDPOINT` is optional; without it, traces are not exported.

## Developing against a local papermake checkout

`papermake` comes from crates.io. To build against a local checkout of
[rkstgr/papermake](https://github.com/rkstgr/papermake) instead, add a
gitignored `.cargo/config.toml`:

```toml
[patch.crates-io]
papermake = { path = "../path/to/papermake/crates/papermake" }
```

# Deploy

First, build and package the lambda function

```sh
just build
```

Then, deploy it to AWS

```sh
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

# Test
```sh
just test
```
