use crate::SandboxError;
use serde::{Deserialize, Serialize};
use std::ffi::c_void;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::ptr::null_mut;
use std::time::{SystemTime, UNIX_EPOCH};
use windows_sys::Win32::Foundation::{CloseHandle, LocalFree, ERROR_SUCCESS, HANDLE};
use windows_sys::Win32::Security::Authorization::{
    ConvertSidToStringSidW, GetNamedSecurityInfoW, SetEntriesInAclW, SetNamedSecurityInfoW,
    EXPLICIT_ACCESS_W, NO_MULTIPLE_TRUSTEE, REVOKE_ACCESS, SE_FILE_OBJECT, TRUSTEE_IS_SID,
    TRUSTEE_IS_UNKNOWN, TRUSTEE_W,
};
use windows_sys::Win32::Security::Isolation::{
    DeleteAppContainerProfile, DeriveAppContainerSidFromAppContainerName,
};
use windows_sys::Win32::Security::{
    FreeSid, ACL, DACL_SECURITY_INFORMATION, NO_INHERITANCE, PSID,
};
use windows_sys::Win32::System::Threading::{OpenProcess, WaitForSingleObject};

const MANIFEST_VERSION: u32 = 1;
const MANIFEST_PREFIX: &str = "origins-sandbox-cleanup-";
const PROCESS_SYNCHRONIZE_ACCESS: u32 = 0x0010_0000;
const WAIT_OBJECT_0_VALUE: u32 = 0;
const WAIT_TIMEOUT_VALUE: u32 = 258;
const ERROR_INVALID_PARAMETER_VALUE: i32 = 87;
const HRESULT_NOT_FOUND: i32 = 0x8007_0490_u32 as i32;
const HRESULT_FILE_NOT_FOUND: i32 = 0x8007_0002_u32 as i32;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CleanupManifest {
    version: u32,
    owner_pid: u32,
    profile_name: String,
    sid_string: String,
    paths: Vec<PathBuf>,
}

pub(crate) struct CleanupRegistration {
    manifest_path: PathBuf,
}

impl CleanupRegistration {
    pub(crate) fn register(profile_name: &str, paths: &[PathBuf]) -> Result<Self, SandboxError> {
        let cleanup_dir = cleanup_dir()?;
        fs::create_dir_all(&cleanup_dir).map_err(io_error)?;
        recover_stale_in(&cleanup_dir)?;

        let mut paths = paths.to_vec();
        paths.sort();
        paths.dedup();
        let sid = DerivedSid::from_profile_name(profile_name)?;
        let manifest = CleanupManifest {
            version: MANIFEST_VERSION,
            owner_pid: std::process::id(),
            profile_name: profile_name.to_owned(),
            sid_string: sid.as_string()?,
            paths,
        };
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|error| SandboxError::Os(format!("system clock invalid: {error}")))?
            .as_nanos();
        let manifest_path = cleanup_dir.join(format!(
            "{MANIFEST_PREFIX}{}-{nonce}.json",
            std::process::id()
        ));
        write_manifest(&manifest_path, &manifest)?;
        if let Err(error) = spawn_watchdog(std::process::id(), &manifest_path) {
            let _ = fs::remove_file(&manifest_path);
            return Err(error);
        }
        Ok(Self { manifest_path })
    }

    pub(crate) fn cleanup_now(&self) -> Result<(), SandboxError> {
        cleanup_manifest_file(&self.manifest_path)
    }
}

pub(crate) fn recover_stale() -> Result<(), SandboxError> {
    let directory = cleanup_dir()?;
    if !directory.exists() {
        return Ok(());
    }
    recover_stale_in(&directory)
}

pub(crate) fn watch_owner(owner_pid: u32, manifest_path: &Path) -> Result<(), SandboxError> {
    if !manifest_path.exists() {
        return Ok(());
    }
    if let Some(handle) = open_process_for_wait(owner_pid)? {
        let result = unsafe {
            // SAFETY: handle was opened with SYNCHRONIZE access and remains owned until closed.
            WaitForSingleObject(handle, u32::MAX)
        };
        unsafe {
            // SAFETY: handle is owned by this function.
            let _ = CloseHandle(handle);
        }
        if result != WAIT_OBJECT_0_VALUE {
            return Err(SandboxError::Os(format!(
                "cleanup watchdog wait failed for process {owner_pid}: result={result}"
            )));
        }
    }
    cleanup_manifest_file(manifest_path)
}

fn revoke_sid_access(path: &Path, sid: PSID) -> Result<(), SandboxError> {
    if !path.exists() {
        return Ok(());
    }
    update_sid_acl(path, sid, 0, REVOKE_ACCESS, NO_INHERITANCE)
}

fn update_sid_acl(
    path: &Path,
    sid: PSID,
    permissions: u32,
    access_mode: i32,
    inheritance: u32,
) -> Result<(), SandboxError> {
    let mut path_wide = wide(path);
    let mut current_dacl: *mut ACL = null_mut();
    let mut descriptor: *mut c_void = null_mut();
    let status = unsafe {
        // SAFETY: output pointers are valid and path is NUL terminated.
        GetNamedSecurityInfoW(
            path_wide.as_ptr(),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            null_mut(),
            null_mut(),
            &mut current_dacl,
            null_mut(),
            &mut descriptor,
        )
    };
    if status != ERROR_SUCCESS {
        return Err(SandboxError::Os(format!(
            "GetNamedSecurityInfoW failed for {}: {status}",
            path.display()
        )));
    }

    let entry = EXPLICIT_ACCESS_W {
        grfAccessPermissions: permissions,
        grfAccessMode: access_mode,
        grfInheritance: inheritance,
        Trustee: TRUSTEE_W {
            pMultipleTrustee: null_mut(),
            MultipleTrusteeOperation: NO_MULTIPLE_TRUSTEE,
            TrusteeForm: TRUSTEE_IS_SID,
            TrusteeType: TRUSTEE_IS_UNKNOWN,
            ptstrName: sid.cast::<u16>(),
        },
    };
    let mut new_dacl: *mut ACL = null_mut();
    let acl_status = unsafe {
        // SAFETY: entry, current ACL and out pointer are valid for this call.
        SetEntriesInAclW(1, &entry, current_dacl, &mut new_dacl)
    };
    if acl_status != ERROR_SUCCESS || new_dacl.is_null() {
        unsafe {
            // SAFETY: descriptor was allocated by GetNamedSecurityInfoW.
            let _ = LocalFree(descriptor);
        }
        return Err(SandboxError::Os(format!(
            "SetEntriesInAclW failed for {}: {acl_status}",
            path.display()
        )));
    }
    let set_status = unsafe {
        // SAFETY: path and ACL are valid for the duration of this call.
        SetNamedSecurityInfoW(
            path_wide.as_mut_ptr(),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            null_mut(),
            null_mut(),
            new_dacl,
            null_mut(),
        )
    };
    unsafe {
        // SAFETY: new_dacl and descriptor were allocated by Windows ACL APIs.
        let _ = LocalFree(new_dacl.cast::<c_void>());
        let _ = LocalFree(descriptor);
    }
    if set_status != ERROR_SUCCESS {
        return Err(SandboxError::Os(format!(
            "SetNamedSecurityInfoW failed for {}: {set_status}",
            path.display()
        )));
    }
    Ok(())
}

fn cleanup_manifest_file(path: &Path) -> Result<(), SandboxError> {
    if !path.exists() {
        return Ok(());
    }
    let manifest = read_manifest(path)?;
    if manifest.version != MANIFEST_VERSION {
        return Err(SandboxError::Invalid(format!(
            "unsupported Windows cleanup manifest version {}",
            manifest.version
        )));
    }
    let sid = DerivedSid::from_profile_name(&manifest.profile_name)?;
    let actual_sid = sid.as_string()?;
    if actual_sid != manifest.sid_string {
        return Err(SandboxError::Invalid(
            "Windows cleanup manifest SID does not match profile name".to_owned(),
        ));
    }

    for target in &manifest.paths {
        revoke_sid_access(target, sid.0)?;
    }
    delete_profile_idempotent(&manifest.profile_name)?;
    fs::remove_file(path).map_err(io_error)?;
    Ok(())
}

fn recover_stale_in(directory: &Path) -> Result<(), SandboxError> {
    for entry in fs::read_dir(directory).map_err(io_error)? {
        let entry = entry.map_err(io_error)?;
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if !name.starts_with(MANIFEST_PREFIX)
            || path.extension().and_then(|value| value.to_str()) != Some("json")
        {
            continue;
        }
        let manifest = read_manifest(&path)?;
        if manifest.owner_pid == std::process::id() {
            continue;
        }
        if process_is_alive(manifest.owner_pid)? {
            continue;
        }
        cleanup_manifest_file(&path)?;
    }
    Ok(())
}

fn process_is_alive(pid: u32) -> Result<bool, SandboxError> {
    let Some(handle) = open_process_for_wait(pid)? else {
        return Ok(false);
    };
    let result = unsafe {
        // SAFETY: handle was opened with SYNCHRONIZE access and remains live for this call.
        WaitForSingleObject(handle, 0)
    };
    unsafe {
        // SAFETY: handle is owned by this function.
        let _ = CloseHandle(handle);
    }
    match result {
        WAIT_OBJECT_0_VALUE => Ok(false),
        WAIT_TIMEOUT_VALUE => Ok(true),
        other => Err(SandboxError::Os(format!(
            "cannot determine cleanup owner process state: pid={pid} wait={other}"
        ))),
    }
}

fn open_process_for_wait(pid: u32) -> Result<Option<HANDLE>, SandboxError> {
    let handle = unsafe {
        // SAFETY: no handle inheritance is requested; pid comes from an Origins-owned manifest.
        OpenProcess(PROCESS_SYNCHRONIZE_ACCESS, 0, pid)
    };
    if !handle.is_null() {
        return Ok(Some(handle));
    }
    let error = std::io::Error::last_os_error();
    if error.raw_os_error() == Some(ERROR_INVALID_PARAMETER_VALUE) {
        return Ok(None);
    }
    Err(SandboxError::Os(format!(
        "OpenProcess({pid}) for cleanup synchronization failed: {error}"
    )))
}

fn spawn_watchdog(owner_pid: u32, manifest_path: &Path) -> Result<(), SandboxError> {
    let executable = std::env::current_exe().map_err(io_error)?;
    Command::new(executable)
        .arg("--cleanup-watch")
        .arg(owner_pid.to_string())
        .arg(manifest_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| SandboxError::Os(format!("cannot spawn Windows cleanup watchdog: {error}")))?;
    Ok(())
}

fn cleanup_dir() -> Result<PathBuf, SandboxError> {
    if let Some(raw) = std::env::var_os("ORIGINS_SANDBOX_CLEANUP_DIR") {
        let path = PathBuf::from(raw);
        if !path.is_absolute() {
            return Err(SandboxError::Invalid(
                "ORIGINS_SANDBOX_CLEANUP_DIR must be absolute".to_owned(),
            ));
        }
        return Ok(path);
    }
    Ok(std::env::temp_dir().join("ttg-origins-sandbox-cleanup"))
}

fn write_manifest(path: &Path, manifest: &CleanupManifest) -> Result<(), SandboxError> {
    let bytes = serde_json::to_vec(manifest)
        .map_err(|error| SandboxError::Invalid(format!("cannot encode cleanup manifest: {error}")))?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(io_error)?;
    file.write_all(&bytes).map_err(io_error)?;
    file.sync_all().map_err(io_error)?;
    Ok(())
}

fn read_manifest(path: &Path) -> Result<CleanupManifest, SandboxError> {
    let bytes = fs::read(path).map_err(io_error)?;
    serde_json::from_slice(&bytes).map_err(|error| {
        SandboxError::Invalid(format!(
            "invalid cleanup manifest {}: {error}",
            path.display()
        ))
    })
}

fn delete_profile_idempotent(name: &str) -> Result<(), SandboxError> {
    let wide_name = wide_text(name);
    let result = unsafe {
        // SAFETY: profile name is NUL terminated and owned for the duration of this call.
        DeleteAppContainerProfile(wide_name.as_ptr())
    };
    if result >= 0 || result == HRESULT_NOT_FOUND || result == HRESULT_FILE_NOT_FOUND {
        return Ok(());
    }
    Err(SandboxError::Os(format!(
        "DeleteAppContainerProfile({name}) failed with HRESULT 0x{:08x}",
        result as u32
    )))
}

struct DerivedSid(PSID);

impl DerivedSid {
    fn from_profile_name(name: &str) -> Result<Self, SandboxError> {
        let wide_name = wide_text(name);
        let mut sid: PSID = null_mut();
        let result = unsafe {
            // SAFETY: profile name is NUL terminated and sid is a valid out pointer.
            DeriveAppContainerSidFromAppContainerName(wide_name.as_ptr(), &mut sid)
        };
        if result < 0 || sid.is_null() {
            return Err(SandboxError::Os(format!(
                "DeriveAppContainerSidFromAppContainerName failed with HRESULT 0x{:08x}",
                result as u32
            )));
        }
        Ok(Self(sid))
    }

    fn as_string(&self) -> Result<String, SandboxError> {
        let mut text: *mut u16 = null_mut();
        let converted = unsafe {
            // SAFETY: self.0 is a valid SID and text is a valid out pointer.
            ConvertSidToStringSidW(self.0, &mut text)
        };
        if converted == 0 || text.is_null() {
            return Err(SandboxError::Os(format!(
                "ConvertSidToStringSidW failed: {}",
                std::io::Error::last_os_error()
            )));
        }
        let value = copy_wide_string(text.cast_const())?;
        unsafe {
            // SAFETY: text was allocated by ConvertSidToStringSidW.
            let _ = LocalFree(text.cast::<c_void>());
        }
        Ok(value)
    }
}

impl Drop for DerivedSid {
    fn drop(&mut self) {
        if !self.0.is_null() {
            unsafe {
                // SAFETY: the SID was allocated by DeriveAppContainerSidFromAppContainerName.
                let _ = FreeSid(self.0);
            }
        }
    }
}

fn copy_wide_string(pointer: *const u16) -> Result<String, SandboxError> {
    if pointer.is_null() {
        return Err(SandboxError::Os(
            "Windows returned a null wide string".to_owned(),
        ));
    }
    let mut length = 0_usize;
    unsafe {
        // SAFETY: Windows returned a NUL-terminated string; this loop remains inside that allocation.
        while *pointer.add(length) != 0 {
            length += 1;
        }
        String::from_utf16(std::slice::from_raw_parts(pointer, length))
            .map_err(|error| SandboxError::Os(format!("Windows returned invalid UTF-16: {error}")))
    }
}

fn wide(path: &Path) -> Vec<u16> {
    path.as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

fn wide_text(value: &str) -> Vec<u16> {
    std::ffi::OsStr::new(value)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

fn io_error(error: std::io::Error) -> SandboxError {
    SandboxError::Io(error.to_string())
}
