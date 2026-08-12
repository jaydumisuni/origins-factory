use std::env;
#[cfg(windows)]
use std::ffi::c_void;
use std::fs::{self, OpenOptions};
use std::io::Write;
#[cfg(windows)]
use std::mem::{size_of, zeroed};
use std::net::{SocketAddr, TcpStream, UdpSocket};
#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;
use std::path::Path;
#[cfg(windows)]
use std::ptr::{null, null_mut};
use std::thread;
use std::time::Duration;
#[cfg(windows)]
use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
#[cfg(windows)]
use windows_sys::Win32::Security::{
    GetTokenInformation, TokenAppContainerSid, SECURITY_CAPABILITIES,
    TOKEN_APPCONTAINER_INFORMATION, TOKEN_QUERY,
};
#[cfg(windows)]
use windows_sys::Win32::System::Threading::{
    CreateProcessW, DeleteProcThreadAttributeList, GetCurrentProcess,
    InitializeProcThreadAttributeList, OpenProcessToken, UpdateProcThreadAttribute,
    EXTENDED_STARTUPINFO_PRESENT, PROCESS_INFORMATION, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
    STARTUPINFOEXW,
};

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
        "tree" => match (args.next(), args.next(), args.next()) {
            (Some(executable), Some(path), None) => tree(&executable, &path),
            _ => EXIT_USAGE,
        },
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
    let address = match address.parse::<SocketAddr>() {
        Ok(address) => address,
        Err(error) => {
            eprintln!("TCP_DENIED: invalid probe address: {error}");
            return EXIT_TCP_DENIED;
        }
    };
    match TcpStream::connect_timeout(&address, Duration::from_secs(2)) {
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

#[cfg(target_os = "linux")]
fn tree(_executable: &str, path: &str) -> i32 {
    let result = unsafe {
        // SAFETY: this proof process is single-threaded at the fork point and the child immediately
        // enters the heartbeat loop without invoking non-async-signal-safe setup code first.
        nix::unistd::fork()
    };
    match result {
        Ok(nix::unistd::ForkResult::Child) => std::process::exit(heartbeat(path)),
        Ok(nix::unistd::ForkResult::Parent { .. }) => loop {
            thread::sleep(Duration::from_secs(1));
        },
        Err(error) => {
            eprintln!("TREE_FAILED: fork: {error}");
            EXIT_TREE_FAILED
        }
    }
}

#[cfg(windows)]
fn tree(executable: &str, path: &str) -> i32 {
    if let Err(error) = spawn_same_appcontainer(executable, path) {
        eprintln!("TREE_FAILED: spawn: {error}");
        return EXIT_TREE_FAILED;
    }
    loop {
        thread::sleep(Duration::from_secs(1));
    }
}

#[cfg(windows)]
fn spawn_same_appcontainer(executable: &str, heartbeat_path: &str) -> Result<(), String> {
    let mut token: HANDLE = null_mut();
    let opened = unsafe {
        // SAFETY: GetCurrentProcess returns the current pseudo-handle and token is a valid out pointer.
        OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token)
    };
    if opened == 0 || token.is_null() {
        return Err(format!(
            "OpenProcessToken failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    let token = Handle(token);

    let mut token_bytes = 0_u32;
    unsafe {
        // SAFETY: first call intentionally queries the required TokenAppContainerSid buffer size.
        let _ = GetTokenInformation(
            token.0,
            TokenAppContainerSid,
            null_mut(),
            0,
            &mut token_bytes,
        );
    }
    if token_bytes < size_of::<TOKEN_APPCONTAINER_INFORMATION>() as u32 {
        return Err("current process does not expose an AppContainer SID".to_owned());
    }
    let token_words = (token_bytes as usize).div_ceil(size_of::<usize>());
    let mut token_storage = vec![0_usize; token_words];
    let got_token = unsafe {
        // SAFETY: token_storage is aligned and large enough for the size returned above.
        GetTokenInformation(
            token.0,
            TokenAppContainerSid,
            token_storage.as_mut_ptr().cast::<c_void>(),
            token_bytes,
            &mut token_bytes,
        )
    };
    if got_token == 0 {
        return Err(format!(
            "GetTokenInformation(TokenAppContainerSid) failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    let token_info = unsafe {
        // SAFETY: token_storage contains TOKEN_APPCONTAINER_INFORMATION returned by Windows.
        &*(token_storage
            .as_ptr()
            .cast::<TOKEN_APPCONTAINER_INFORMATION>())
    };
    if token_info.TokenAppContainer.is_null() {
        return Err("current process is not running inside an AppContainer".to_owned());
    }

    let attributes = ChildAttributeList::new(token_info.TokenAppContainer)?;
    let mut startup: STARTUPINFOEXW = unsafe { zeroed() };
    startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
    startup.lpAttributeList = attributes.ptr;

    let executable_wide = wide(executable);
    let mut command_line = wide(&format!(
        "\"{}\" heartbeat \"{}\"",
        executable.replace('"', ""),
        heartbeat_path.replace('"', "")
    ));
    let mut process: PROCESS_INFORMATION = unsafe { zeroed() };
    let created = unsafe {
        // SAFETY: application and command-line buffers are live and NUL-terminated; the attribute
        // list binds the descendant to the same AppContainer SID as the already-authorized parent.
        CreateProcessW(
            executable_wide.as_ptr(),
            command_line.as_mut_ptr(),
            null(),
            null(),
            0,
            EXTENDED_STARTUPINFO_PRESENT,
            null(),
            null(),
            &startup.StartupInfo,
            &mut process,
        )
    };
    if created == 0 {
        return Err(format!(
            "CreateProcessW(same AppContainer) failed: {}",
            std::io::Error::last_os_error()
        ));
    }
    let process_handle = Handle(process.hProcess);
    let thread_handle = Handle(process.hThread);
    drop(thread_handle);
    drop(process_handle);
    Ok(())
}

#[cfg(windows)]
struct ChildAttributeList {
    storage: Vec<usize>,
    ptr: *mut c_void,
    _capabilities: Box<SECURITY_CAPABILITIES>,
}

#[cfg(windows)]
impl ChildAttributeList {
    fn new(appcontainer_sid: *mut c_void) -> Result<Self, String> {
        let mut bytes = 0_usize;
        unsafe {
            // SAFETY: first call only queries the required allocation size.
            let _ = InitializeProcThreadAttributeList(null_mut(), 1, 0, &mut bytes);
        }
        if bytes == 0 {
            return Err(format!(
                "InitializeProcThreadAttributeList size query failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        let words = bytes.div_ceil(size_of::<usize>());
        let mut storage = vec![0_usize; words];
        let ptr = storage.as_mut_ptr().cast::<c_void>();
        let initialized = unsafe {
            // SAFETY: storage is aligned and large enough for the requested attribute list.
            InitializeProcThreadAttributeList(ptr, 1, 0, &mut bytes)
        };
        if initialized == 0 {
            return Err(format!(
                "InitializeProcThreadAttributeList failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        let mut capabilities = Box::new(SECURITY_CAPABILITIES {
            AppContainerSid: appcontainer_sid,
            Capabilities: null_mut(),
            CapabilityCount: 0,
            Reserved: 0,
        });
        let updated = unsafe {
            // SAFETY: capabilities is boxed and remains live for the lifetime of this attribute list.
            UpdateProcThreadAttribute(
                ptr,
                0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES as usize,
                (&mut *capabilities as *mut SECURITY_CAPABILITIES).cast::<c_void>(),
                size_of::<SECURITY_CAPABILITIES>(),
                null_mut(),
                null_mut(),
            )
        };
        if updated == 0 {
            unsafe {
                // SAFETY: ptr references a successfully initialized attribute list.
                DeleteProcThreadAttributeList(ptr);
            }
            return Err(format!(
                "UpdateProcThreadAttribute(security capabilities) failed: {}",
                std::io::Error::last_os_error()
            ));
        }
        Ok(Self {
            storage,
            ptr,
            _capabilities: capabilities,
        })
    }
}

#[cfg(windows)]
impl Drop for ChildAttributeList {
    fn drop(&mut self) {
        if !self.storage.is_empty() {
            unsafe {
                // SAFETY: ptr references an initialized attribute list backed by storage.
                DeleteProcThreadAttributeList(self.ptr);
            }
        }
    }
}

#[cfg(windows)]
struct Handle(HANDLE);

#[cfg(windows)]
impl Drop for Handle {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe {
                // SAFETY: this wrapper owns the Windows handle exactly once.
                let _ = CloseHandle(self.0);
            }
        }
    }
}

#[cfg(windows)]
fn wide(value: &str) -> Vec<u16> {
    std::ffi::OsStr::new(value)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

#[cfg(not(any(target_os = "linux", windows)))]
fn tree(_executable: &str, _path: &str) -> i32 {
    EXIT_TREE_FAILED
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
