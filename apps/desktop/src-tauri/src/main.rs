// The extra attribute stops a console window opening behind the app on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    hawkvance_lib::run()
}
