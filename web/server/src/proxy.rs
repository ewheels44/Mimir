use axum::{http::StatusCode, response::IntoResponse, Json};

static CLIENT: std::sync::OnceLock<reqwest::Client> = std::sync::OnceLock::new();

fn client() -> &'static reqwest::Client {
    CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(120))
            .build()
            .expect("failed to build reqwest client")
    })
}

pub async fn forward_post(port: u16, path: &str, body: serde_json::Value) -> impl IntoResponse {
    let url = format!("http://127.0.0.1:{}{}", port, path);
    match client().post(&url).json(&body).send().await {
        Ok(resp) => match resp.json::<serde_json::Value>().await {
            Ok(v) => Json(v).into_response(),
            Err(e) => (StatusCode::BAD_GATEWAY, e.to_string()).into_response(),
        },
        Err(e) => (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Sidecar unreachable: {}", e),
        )
            .into_response(),
    }
}

pub async fn forward_get(port: u16, path: &str) -> impl IntoResponse {
    let url = format!("http://127.0.0.1:{}{}", port, path);
    match client().get(&url).send().await {
        Ok(resp) => match resp.json::<serde_json::Value>().await {
            Ok(v) => Json(v).into_response(),
            Err(e) => (StatusCode::BAD_GATEWAY, e.to_string()).into_response(),
        },
        Err(e) => (
            StatusCode::SERVICE_UNAVAILABLE,
            format!("Sidecar unreachable: {}", e),
        )
            .into_response(),
    }
}
