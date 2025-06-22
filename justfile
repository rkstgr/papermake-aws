build:
    cargo lambda build --release --arm64
    just zip

zip:
    cd lambda_functions/renderer && just zip
    cd lambda_functions/request_handler && just zip

apply:
    cd terraform/environments/dev && terraform apply -auto-approve

test:
    uv run run_perf_test.py --template $TEST_TEMPLATE --endpoint $TEST_ENDPOINT --bucket $TEST_BUCKET --requests 200 --batch-size 40 --concurrency 10
