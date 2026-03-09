use tauri::Manager;

/// PropEdge Tauri Application
/// Wraps the React frontend into a native desktop app.
/// The Python backend runs separately (locally or on EC2).

#[tauri::command]
fn greet(name: &str) -> String {
    format!("PropEdge ready, {}! System online.", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_websocket::init())
        .invoke_handler(tauri::generate_handler![greet])
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let window = app.get_webview_window("main").unwrap();
                window.open_devtools();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running PropEdge");
}
