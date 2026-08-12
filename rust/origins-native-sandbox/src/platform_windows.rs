use crate::windows_cleanup::CleanupRegistration;
use crate::{SandboxError, SandboxPathRule, SandboxSpec};
use std::ffi::{c_void, OsString};
use std::mem::{size_of, zeroed};
use std::os::windows::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};
use std::ptr::{null, null_mut};
use std::time::{SystemTime, UNIX_EPOCH};
use windows_sys::Win32::Foundation::{CloseHandle, LocalFree, ERROR_SUCCESS, HANDLE};
use windows_sys::Win32::Security::Authorization::{
    ConvertSidToStringSidW, GetNamedSecurityInfoW, SetEntriesInAclW, SetNamedSecurityInfoW,
    EXPLICIT_ACCESS_W, GRANT_ACCESS, NO_MULTIPLE_TRUSTEE, SE_FILE_OBJECT, TRUSTEE_IS_SID,
    TRUSTEE_IS_UNKNOWN, TRUSTEE_W,
};
use windows_sys::Win32::Security::Isolation::{CreateAppContainerProfile, GetAppContainerFolderPath};
use windows_sys::Win32::Security::{
    FreeSid, ACL, DACL_SECURITY_INFORMATION, NO_INHERITANCE, PSID, SECURITY_CAPABILITIES,
    SUB_CONTAINERS_AND_OBJECTS_INHERIT,
};
use windows_sys::Win32::Storage::FileSystem::{
    FILE_GENERIC_EXECUTE, FILE_GENERIC_READ, FILE_GENERIC_WRITE,
};
use windows_sys::Win32::System::Com::CoTaskMemFree;
use windows_sys::Win32::System::Environment::{CreateEnvironmentBlock, DestroyEnvironmentBlock};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows_sys::Win32::System::Threading::{
    CreateProcessW, DeleteProcThreadAttributeList, GetExitCodeProcess,
    InitializeProcThreadAttributeList, ResumeThread, UpdateProcThreadAttribute,
    WaitForSingleObject, CREATE_SUSPENDED, CREATE_UNICODE_ENVIRONMENT,
    EXTENDED_STARTUPINFO_PRESENT, INFINITE, PROCESS_INFORMATION,
    PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, STARTUPINFOEXW,
};

pub fn run(spec: SandboxSpec) -> Result<i32, SandboxError> {
    let profile = AppContainerProfile::create(&spec)?;
    let appcontainer_local = appcontainer_local_path(profile.sid)?;
    let mut grants = Vec::new();
    grants.push(AclGrant::apply(
        &spec.executable,
        profile.sid,
        FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
        false,
    )?);
    for path in &spec.runtime_read_paths {
        grants.push(AclGrant::apply(
            path,
            profile.sid,
            FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
            path.is_dir(),
        )?);
    }
    for rule in &spec.resource_paths {
        grants.push(apply_resource_grant(rule, profile.sid)?);
    }

    let job = JobHandle::create()?;
    let attributes = AttributeList::security_capabilities(profile.sid)?;
    let mut startup: STARTUPINFOEXW = unsafe { zeroed() };
    startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
    startup.lpAttributeList = attributes.ptr;

    let executable = wide(&spec.executable);
    let cwd = wide(&spec.cwd);
    let mut command_line = command_line(&spec.executable, &spec.args);
    let environment = environment_block(&spec.environment, &spec.cwd, &appcontainer_local)?;
    let mut process: PROCESS_INFORMATION = unsafe { zeroed() };
    let created = unsafe {
        // SAFETY: all pointers reference live, NUL-terminated buffers for the duration of CreateProcessW.
        CreateProcessW(
            executable.as_ptr(),
            command_line.as_mut_ptr(),
            null(),
            null(),
            0,
            CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT,
            environment.as_ptr().cast::<c_void>(),
            cwd.as_ptr(),
            &startup.StartupInfo,
            &mut process,
        )
    };
    if created == 0 {
        return Err(last_os_error("CreateProcessW(AppContainer) failed"));
    }
    let process_guard = ProcessHandles::new(process.hProcess, process.hThread);
    let assigned = unsafe {
        // SAFETY: both handles are valid and owned for the duration of this call.
        AssignProcessToJobObject(job.handle, process_guard.process)
    };
    if assigned == 0 {
        return Err(last_os_error("AssignProcessToJobObject failed"));
    }
    let resumed = unsafe {
        // SAFETY: the primary thread handle belongs to the newly created suspended process.
        ResumeThread(process_guard.thread)
    };
    if resumed == u32::MAX {
        return Err(last_os_error("ResumeThread failed"));
    }

    unsafe {
        // SAFETY: process handle remains valid until process_guard drops.
        WaitForSingleObject(process_guard.process, INFINITE);
    }
    let mut exit_code = 0_u32;
    let got_exit = unsafe {
        // SAFETY: process is signaled and the handle remains valid.
        GetExitCodeProcess(process_guard.process, &mut exit_code)
    };
    if got_exit == 0 {
        return Err(last_os_error("GetExitCodeProcess failed"));
    }

    drop(process_guard);
    drop(job);
    drop(attributes);
    drop(grants);
    drop(profile);
    Ok(exit_code as i32)
}

fn apply_resource_grant(rule: &SandboxPathRule, sid: PSID) -> Result<AclGrant, SandboxError> {
    let mut permissions = FILE_GENERIC_READ | FILE_GENERIC_EXECUTE;
    if rule.writable {
        permissions |= FILE_GENERIC_WRITE;
    }
    AclGrant::apply(&rule.path, sid, permissions, rule.path.is_dir())
}

struct AppContainerProfile {
    sid: PSID,
    cleanup: CleanupRegistration,
}

impl AppContainerProfile {
    fn create(spec: &SandboxSpec) -> Result<Self, SandboxError> {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|error| SandboxError::Os(format!("system clock invalid: {error}")))?
            .as_nanos();
        let name_text = format!("TTG.Origins.{}.{}", std::process::id(), nonce);
        let mut cleanup_paths = vec![spec.executable.clone()];
        cleanup_paths.extend(spec.runtime_read_paths.iter().cloned());
        cleanup_paths.extend(spec.resource_paths.iter().map(|rule| rule.path.clone()));
        let cleanup = CleanupRegistration::register(&name_text, &cleanup_paths)?;

        let name = wide_text(&name_text);
        let display = wide_text("THETECHGUY Origins Sandbox");
        let description = wide_text("Ephemeral Origins capability containment profile");
        let mut sid: PSID = null_mut();
        let result = unsafe {
            // SAFETY: strings are NUL terminated; no capability array is supplied; sid is an out pointer.
            CreateAppContainerProfile(
                name.as_ptr(),
                display.as_ptr(),
                description.as_ptr(),
                null(),
                0,
                &mut sid,
            )
        };
        if result < 0 || sid.is_null() {
            let _ = cleanup.cleanup_now();
            return Err(SandboxError::Os(format!(
                "CreateAppContainerProfile failed with HRESULT 0x{:08x}",
                result as u32
            )));
        }
        Ok(Self { sid, cleanup })
    }
}

impl Drop for AppContainerProfile {
    fn drop(&mut self) {
        let _ = self.cleanup.cleanup_now();
        if !self.sid.is_null() {
            unsafe {
                // SAFETY: SID is the resource returned by CreateAppContainerProfile.
                let _ = FreeSid(self.sid);
            }
        }
    }
}

fn appcontainer_local_path(sid: PSID) -> Result<PathBuf, SandboxError> {
    let mut sid_text: *mut u16 = null_mut();
    let converted = unsafe {
        // SAFETY: sid is owned by the live AppContainer profile and sid_text is a valid out pointer.
        ConvertSidToStringSidW(sid, &mut sid_text)
    };
    if converted == 0 || sid_text.is_null() {
        return Err(last_os_error("ConvertSidToStringSidW failed"));
    }

    let mut folder: *mut u16 = null_mut();
    let result = unsafe {
        // SAFETY: sid_text is a live NUL-terminated SID string and folder is a valid out pointer.
        GetAppContainerFolderPath(sid_text, &mut folder)
    };
    unsafe {
        // SAFETY: sid_text was allocated by ConvertSidToStringSidW.
        let _ = LocalFree(sid_text.cast::<c_void>());
    }
    if result < 0 || folder.is_null() {
        return Err(SandboxError::Os(format!(
            "GetAppContainerFolderPath failed with HRESULT 0x{:08x}",
            result as u32
        )));
    }

    let path = copy_wide_string(folder.cast_const())?;
    unsafe {
        // SAFETY: folder was allocated by GetAppContainerFolderPath and must be freed with CoTaskMemFree.
        CoTaskMemFree(folder.cast::<c_void>());
    }
    Ok(PathBuf::from(path))
}

struct AclGrant;

impl AclGrant {
    fn apply(
        path: &Path,
        sid: PSID,
        permissions: u32,
        inherit: bool,
    ) -> Result<Self, SandboxError> {
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
            grfAccessMode: GRANT_ACCESS,
            grfInheritance: if inherit {
                SUB_CONTAINERS_AND_OBJECTS_INHERIT
            } else {
                NO_INHERITANCE
            },
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
            // SAFETY: both allocations are no longer needed after SetNamedSecurityInfoW returns.
            let _ = LocalFree(new_dacl.cast::<c_void>());
            let _ = LocalFree(descriptor);
        }
        if set_status != ERROR_SUCCESS {
            return Err(SandboxError::Os(format!(
                "SetNamedSecurityInfoW failed for {}: {set_status}",
                path.display()
            )));
        }
        // Normal and crash cleanup both revoke only this ephemeral AppContainer SID through
        // CleanupRegistration. We deliberately do not restore a whole saved DACL here because doing
        // so could overwrite an unrelated ACL mutation made while the sandbox was running.
        Ok(Self)
    }
}

struct AttributeList {
    storage: Vec<usize>,
    ptr: *mut c_void,
    _capabilities: Box<SECURITY_CAPABILITIES>,
}

impl AttributeList {
    fn security_capabilities(sid: PSID) -> Result<Self, SandboxError> {
        let mut bytes = 0_usize;
        unsafe {
            // SAFETY: first call only queries the required buffer size.
            let _ = InitializeProcThreadAttributeList(null_mut(), 1, 0, &mut bytes);
        }
        if bytes == 0 {
            return Err(last_os_error(
                "InitializeProcThreadAttributeList size query failed",
            ));
        }
        let words = bytes.div_ceil(size_of::<usize>());
        let mut storage = vec![0_usize; words];
        let ptr = storage.as_mut_ptr().cast::<c_void>();
        let initialized = unsafe {
            // SAFETY: storage is aligned and has at least the requested byte length.
            InitializeProcThreadAttributeList(ptr, 1, 0, &mut bytes)
        };
        if initialized == 0 {
            return Err(last_os_error("InitializeProcThreadAttributeList failed"));
        }
        let mut capabilities = Box::new(SECURITY_CAPABILITIES {
            AppContainerSid: sid,
            Capabilities: null_mut(),
            CapabilityCount: 0,
            Reserved: 0,
        });
        let updated = unsafe {
            // SAFETY: the boxed capability value is owned by AttributeList and remains live until
            // DeleteProcThreadAttributeList runs in Drop, as required by UpdateProcThreadAttribute.
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
                // SAFETY: ptr refers to an initialized attribute list.
                DeleteProcThreadAttributeList(ptr);
            }
            return Err(last_os_error("UpdateProcThreadAttribute failed"));
        }
        Ok(Self {
            storage,
            ptr,
            _capabilities: capabilities,
        })
    }
}

impl Drop for AttributeList {
    fn drop(&mut self) {
        if !self.storage.is_empty() {
            unsafe {
                // SAFETY: ptr refers to an initialized attribute list backed by storage.
                DeleteProcThreadAttributeList(self.ptr);
            }
        }
    }
}

struct JobHandle {
    handle: HANDLE,
}

impl JobHandle {
    fn create() -> Result<Self, SandboxError> {
        let handle = unsafe {
            // SAFETY: no security attributes or external name are supplied.
            CreateJobObjectW(null(), null())
        };
        if handle.is_null() {
            return Err(last_os_error("CreateJobObjectW failed"));
        }
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { zeroed() };
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let configured = unsafe {
            // SAFETY: handle is valid and limits points to the expected information structure.
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast::<c_void>(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if configured == 0 {
            unsafe {
                let _ = CloseHandle(handle);
            }
            return Err(last_os_error("SetInformationJobObject failed"));
        }
        Ok(Self { handle })
    }
}

impl Drop for JobHandle {
    fn drop(&mut self) {
        unsafe {
            // SAFETY: handle is owned by this guard; kill-on-close fences the entire process tree.
            let _ = CloseHandle(self.handle);
        }
    }
}

struct ProcessHandles {
    process: HANDLE,
    thread: HANDLE,
}

impl ProcessHandles {
    fn new(process: HANDLE, thread: HANDLE) -> Self {
        Self { process, thread }
    }
}

impl Drop for ProcessHandles {
    fn drop(&mut self) {
        unsafe {
            // SAFETY: handles are owned by this guard.
            let _ = CloseHandle(self.thread);
            let _ = CloseHandle(self.process);
        }
    }
}

fn environment_block(
    environment: &std::collections::BTreeMap<String, String>,
    cwd: &Path,
    appcontainer_local: &Path,
) -> Result<Vec<u16>, SandboxError> {
    let mut raw: *mut c_void = null_mut();
    let created = unsafe {
        // SAFETY: raw is a valid out pointer; NULL token and inherit=false request system variables only.
        CreateEnvironmentBlock(&mut raw, null_mut(), 0)
    };
    if created == 0 || raw.is_null() {
        return Err(last_os_error("CreateEnvironmentBlock(system-only) failed"));
    }
    let copied = copy_environment_entries(raw.cast::<u16>());
    unsafe {
        // SAFETY: raw is the buffer returned by CreateEnvironmentBlock.
        let _ = DestroyEnvironmentBlock(raw.cast_const());
    }
    let mut entries = copied?;

    for (name, value) in environment {
        upsert_environment_entry(&mut entries, name, value);
    }

    let local_text = appcontainer_local.to_string_lossy();
    let temp_text = appcontainer_local.join("Temp").to_string_lossy().into_owned();
    upsert_environment_entry(&mut entries, "LOCALAPPDATA", &local_text);
    upsert_environment_entry(&mut entries, "TEMP", &temp_text);
    upsert_environment_entry(&mut entries, "TMP", &temp_text);

    let cwd_text = cwd.to_string_lossy();
    let cwd_bytes = cwd_text.as_bytes();
    if cwd_bytes.len() >= 3 && cwd_bytes[0].is_ascii_alphabetic() && cwd_bytes[1] == b':' {
        let drive_name = format!("={}", &cwd_text[..2]);
        upsert_environment_entry(&mut entries, &drive_name, &cwd_text);
    }
    entries.sort_by_key(|entry| entry.to_ascii_uppercase());

    let mut block = Vec::new();
    for entry in entries {
        block.extend(entry.encode_utf16());
        block.push(0);
    }
    block.push(0);
    Ok(block)
}

fn copy_environment_entries(raw: *const u16) -> Result<Vec<String>, SandboxError> {
    const MAX_CODE_UNITS: usize = 1_048_576;
    let mut entries = Vec::new();
    let mut offset = 0_usize;
    loop {
        if offset >= MAX_CODE_UNITS {
            return Err(SandboxError::Os(
                "system environment block exceeded safety bound".to_owned(),
            ));
        }
        let first = unsafe {
            // SAFETY: raw points to a Windows environment block terminated by a double NUL.
            *raw.add(offset)
        };
        if first == 0 {
            break;
        }
        let start = offset;
        while offset < MAX_CODE_UNITS {
            let current = unsafe {
                // SAFETY: offset remains within the explicit safety bound while scanning the API buffer.
                *raw.add(offset)
            };
            if current == 0 {
                break;
            }
            offset += 1;
        }
        if offset >= MAX_CODE_UNITS {
            return Err(SandboxError::Os(
                "system environment entry exceeded safety bound".to_owned(),
            ));
        }
        let units = unsafe {
            // SAFETY: start..offset was scanned from the live environment block and excludes the NUL.
            std::slice::from_raw_parts(raw.add(start), offset - start)
        };
        let entry = String::from_utf16(units).map_err(|error| {
            SandboxError::Os(format!("system environment contains invalid UTF-16: {error}"))
        })?;
        entries.push(entry);
        offset += 1;
    }
    Ok(entries)
}

fn copy_wide_string(raw: *const u16) -> Result<OsString, SandboxError> {
    const MAX_CODE_UNITS: usize = 32_768;
    let mut len = 0_usize;
    while len < MAX_CODE_UNITS {
        let current = unsafe {
            // SAFETY: raw points to a NUL-terminated string returned by a Windows API.
            *raw.add(len)
        };
        if current == 0 {
            let units = unsafe {
                // SAFETY: 0..len was scanned from the live NUL-terminated API string.
                std::slice::from_raw_parts(raw, len)
            };
            return Ok(OsString::from_wide(units));
        }
        len += 1;
    }
    Err(SandboxError::Os(
        "Windows API string exceeded safety bound".to_owned(),
    ))
}

fn upsert_environment_entry(entries: &mut Vec<String>, name: &str, value: &str) {
    entries.retain(|entry| !environment_entry_name(entry).eq_ignore_ascii_case(name));
    entries.push(format!("{name}={value}"));
}

fn environment_entry_name(entry: &str) -> &str {
    let search_start = usize::from(entry.starts_with('='));
    entry[search_start..]
        .find('=')
        .map(|index| &entry[..search_start + index])
        .unwrap_or(entry)
}

fn command_line(executable: &Path, args: &[String]) -> Vec<u16> {
    let mut text = quote_arg(&executable.to_string_lossy());
    for arg in args {
        text.push(' ');
        text.push_str(&quote_arg(arg));
    }
    wide_text(&text)
}

fn quote_arg(arg: &str) -> String {
    if !arg.is_empty() && !arg.chars().any(|ch| ch.is_whitespace() || ch == '"') {
        return arg.to_owned();
    }
    let mut out = String::from("\"");
    let mut backslashes = 0_usize;
    for ch in arg.chars() {
        if ch == '\\' {
            backslashes += 1;
            continue;
        }
        if ch == '"' {
            out.extend(std::iter::repeat('\\').take(backslashes * 2 + 1));
            out.push('"');
            backslashes = 0;
            continue;
        }
        out.extend(std::iter::repeat('\\').take(backslashes));
        backslashes = 0;
        out.push(ch);
    }
    out.extend(std::iter::repeat('\\').take(backslashes * 2));
    out.push('"');
    out
}

fn wide(path: &Path) -> Vec<u16> {
    path.as_os_str().encode_wide().chain(Some(0)).collect()
}

fn wide_text(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(Some(0)).collect()
}

fn last_os_error(context: &str) -> SandboxError {
    SandboxError::Os(format!("{context}: {}", std::io::Error::last_os_error()))
}
