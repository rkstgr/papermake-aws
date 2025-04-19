# Local

Run the lambda function locally

```
cargo lambda watch
```

and in another terminal, invoke it

```
cargo lambda invoke --data-example apigw2-http --output-format json
```

# Deploy

First, build the lambda function

```
cargo lambda build --release --arm64
```

Then, deploy the lambda function to AWS

```
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```
