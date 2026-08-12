use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::net::{TcpStream, UdpSocket};
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

const EXIT_USAGE: i32 = 64;
const EXIT_READ_DENIED: i32 = 41;
const EXIT_WRITE_DENIED: i32 = 42;
const EXIT_TCP_DENIED: i32 = 43;
const EXIT_UDP_DENIED: i32 = 44;
const EXIT_TREE_FAILED: i32 = 45;
const EXIT_HEARTBEAT_FAILED: i32 = 46;

fn main() {
    let mut args = env::args().skip(1);
    let Some(command) = args.next() else {
        std::process::exit(EXIT_USAGE);
    };
    let exit = match command.as_str() {
        "read" => args
            .next()
            .filter(|_| args.next().is_none())
            .map_or(EXIT_USAGE, |path| read(&path)),
        "write" => match (args.next(), args.next(), args.next()) {
            (Some(path), Some(text), None) => write(&path, &text),
            _ => EXIT_USAGE,
        },
        "tcp" => args
            .next()
            .filter(|_| args.next().is_none())
            .map_or(EXIT_USAGE, |address| tcp(&address)),
        "udp" => args
            .next()
            .filter(|_| args.next().is_none())
            .map_or(EXIT_USAGE, |address| udp(&address)),
        "tree" => args
            .next()
            .filter(|_| args.next().is_none())
            .map_or(EXIT_USAGE, |path| tree(&path)),
        "heartbeat" => args
            .next()
            .filter(|_| args.next().is_none())
            .map_or(EXIT_USAGE, |path| heartbeat(&path)),
        _ => EXIT_USAGE,
    };
    std::process::exit(exit);
}

fn read(path: &str) -> i32 {
    match fs::read_to_string(path) {
        Ok(content) => {
            print!("{content}");
            0
        }
        Err(error) => {
            eprintln!("READ_DENIED: {error}");
            EXIT_READ_DENIED
        }
    }
}

fn write(path: &str, text: &str) -> i32 {
    match fs::write(path, text.as_bytes()) {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("WRITE_DENIED: {error}");
            EXIT_WRITE_DENIED
        }
    }
}

fn tcp(address: &str) -> i32 {
    match TcpStream::connect(address) {
        Ok(mut stream) => match stream.write_all(b"origins-tcp-probe") {
            Ok(()) => 0,
            Err(error) => {
                eprintln!("TCP_DENIED: {error}");
                EXIT_TCP_DENIED
            }
        },
        Err(error) => {
            eprintln!("TCP_DENIED: {error}");
            EXIT_TCP_DENIED
        }
    }
}

fn udp(address: &str) -> i32 {
    let bind = if address.starts_with('[') {
        "[::]:0"
    } else {
        "0.0.0.0:0"
    };
    match UdpSocket::bind(bind).and_then(|socket| socket.send_to(b"origins-udp-probe", address)) {
        Ok(_) => 0,
        Err(error) => {
            eprintln!("UDP_DENIED: {error}");
            EXIT_UDP_DENIED
        }
    }
}

fn tree(path: &str) -> i32 {
    let executable = match env::current_exe() {
        Ok(executable) => executable,
        Err(error) => {
            eprintln!("TREE_FAILED: current_exe: {error}");
            return EXIT_TREE_FAILED;
        }
    };
    let child = Command::new(executable)
        .arg("heartbeat")
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();
    if let Err(error) = child {
        eprintln!("TREE_FAILED: spawn: {error}");
        return EXIT_TREE_FAILED;
    }
    loop {
        thread::sleep(Duration::from_secs(1));
    }
}

fn heartbeat(path: &str) -> i32 {
    let path = Path::new(path);
    loop {
        let result = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .and_then(|mut file| file.write_all(b"x\n"));
        if let Err(error) = result {
            eprintln!("HEARTBEAT_FAILED: {error}");
            return EXIT_HEARTBEAT_FAILED;
        }
        thread::sleep(Duration::from_millis(100));
    }
}
