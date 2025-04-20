build:
    cargo lambda build --release --arm64
    just zip
    
zip:
    cd lambda_functions/renderer && just zip
    cd lambda_functions/request_handler && just zip
