build:
    cargo lambda build --release --arm64
    just zip

zip:
    cd lambda_functions/renderer && just zip

apply:
    cd terraform/environments/dev && terraform apply -auto-approve

smalltest:
    uv run run_perf_test.py --template $TEST_TEMPLATE --endpoint $TEST_ENDPOINT --bucket $TEST_BUCKET --requests 6 --batch-size 3 --concurrency 2

test:
    uv run run_perf_test.py --template $TEST_TEMPLATE --endpoint $TEST_ENDPOINT --bucket $TEST_BUCKET --requests 100 --batch-size 25 --concurrency 4

bigtest:
    uv run run_perf_test.py --template $TEST_TEMPLATE --endpoint $TEST_ENDPOINT --bucket $TEST_BUCKET --requests 8000 --batch-size 40 --concurrency 100
