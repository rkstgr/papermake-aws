# Local

Run the lambda function locally

```sh
cd lambda_functions/request_handler
cargo lambda watch
```

and in another terminal, invoke it

```sh
cargo lambda invoke --data-example apigw2-http --output-format json
```

# Deploy

First, build and package both lambda functions

```sh
just build
```

Then, deploy the lambda function to AWS

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
