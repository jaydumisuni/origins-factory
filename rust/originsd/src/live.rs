use crate::store::Store;
use axum::response::sse::{Event, KeepAlive, Sse};
use serde_json::{json, Value};
use std::convert::Infallible;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio::time::sleep;
use tokio_stream::wrappers::ReceiverStream;

pub type LiveStream = Sse<ReceiverStream<Result<Event, Infallible>>>;

const JOURNAL_PAGE: u64 = 100;
const OUTPUT_PAGE: u64 = 64 * 1024;
const POLL_INTERVAL: Duration = Duration::from_millis(75);

pub fn journal_stream(store: Store, after_sequence: u64) -> LiveStream {
    let (sender, receiver) = mpsc::channel(32);
    tokio::spawn(async move {
        let mut cursor = after_sequence;
        loop {
            match store.list_events_after(cursor, JOURNAL_PAGE) {
                Ok(page) => {
                    if page.events.is_empty() {
                        sleep(POLL_INTERVAL).await;
                        continue;
                    }
                    for event in page.events {
                        let sequence = match event["sequence"].as_u64() {
                            Some(sequence) => sequence,
                            None => {
                                send_error(
                                    &sender,
                                    "CORRUPT_STATE",
                                    "journal event sequence missing",
                                )
                                .await;
                                return;
                            }
                        };
                        let data = match serde_json::to_string(&event) {
                            Ok(data) => data,
                            Err(error) => {
                                send_error(&sender, "SERIALIZATION_ERROR", &error.to_string())
                                    .await;
                                return;
                            }
                        };
                        let frame = Event::default()
                            .event("journal")
                            .id(sequence.to_string())
                            .data(data);
                        if sender.send(Ok(frame)).await.is_err() {
                            return;
                        }
                        cursor = sequence;
                    }
                }
                Err(error) => {
                    send_error(&sender, "EVENT_STREAM_FAILED", &error.to_string()).await;
                    return;
                }
            }
        }
    });

    Sse::new(ReceiverStream::new(receiver)).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(10))
            .text("origins-live"),
    )
}

pub fn output_stream(
    store: Store,
    session_id: String,
    stdout_after: u64,
    stderr_after: u64,
) -> LiveStream {
    let (sender, receiver) = mpsc::channel(32);
    tokio::spawn(async move {
        let mut stdout_cursor = stdout_after;
        let mut stderr_cursor = stderr_after;
        loop {
            match store.read_output_delta(&session_id, stdout_cursor, stderr_cursor, OUTPUT_PAGE) {
                Ok(delta) => {
                    let stdout_next = match delta["stdout"]["next"].as_u64() {
                        Some(value) => value,
                        None => {
                            send_error(&sender, "CORRUPT_STATE", "stdout cursor missing").await;
                            return;
                        }
                    };
                    let stderr_next = match delta["stderr"]["next"].as_u64() {
                        Some(value) => value,
                        None => {
                            send_error(&sender, "CORRUPT_STATE", "stderr cursor missing").await;
                            return;
                        }
                    };
                    let has_new_output = stdout_next > stdout_cursor || stderr_next > stderr_cursor;
                    if has_new_output {
                        let data = match serde_json::to_string(&delta) {
                            Ok(data) => data,
                            Err(error) => {
                                send_error(&sender, "SERIALIZATION_ERROR", &error.to_string())
                                    .await;
                                return;
                            }
                        };
                        let frame = Event::default()
                            .event("output")
                            .id(format!("{stdout_next}:{stderr_next}"))
                            .data(data);
                        if sender.send(Ok(frame)).await.is_err() {
                            return;
                        }
                        stdout_cursor = stdout_next;
                        stderr_cursor = stderr_next;
                    }

                    let state = delta["state"].as_str().unwrap_or("");
                    if is_terminal_state(state) {
                        let terminal = json!({
                            "session_id": session_id,
                            "state": state,
                            "stdout_cursor": stdout_cursor,
                            "stderr_cursor": stderr_cursor
                        });
                        let data = serde_json::to_string(&terminal)
                            .unwrap_or_else(|_| "{\"state\":\"terminal\"}".to_owned());
                        let frame = Event::default()
                            .event("terminal")
                            .id(format!("{stdout_cursor}:{stderr_cursor}"))
                            .data(data);
                        let _ = sender.send(Ok(frame)).await;
                        return;
                    }
                    if !has_new_output {
                        sleep(POLL_INTERVAL).await;
                    }
                }
                Err(error) => {
                    send_error(&sender, "OUTPUT_STREAM_FAILED", &error.to_string()).await;
                    return;
                }
            }
        }
    });

    Sse::new(ReceiverStream::new(receiver)).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(10))
            .text("origins-output-live"),
    )
}

fn is_terminal_state(state: &str) -> bool {
    matches!(state, "completed" | "failed" | "interrupted" | "timed_out")
}

async fn send_error(sender: &mpsc::Sender<Result<Event, Infallible>>, code: &str, message: &str) {
    let payload: Value = json!({"error_code": code, "error": message});
    let data = serde_json::to_string(&payload)
        .unwrap_or_else(|_| "{\"error_code\":\"STREAM_ERROR\"}".to_owned());
    let _ = sender
        .send(Ok(Event::default().event("error").data(data)))
        .await;
}
