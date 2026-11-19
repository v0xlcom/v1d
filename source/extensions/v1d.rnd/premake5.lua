local ext = get_current_extension_info()
project_ext(ext)
repo_build.prebuild_link {
    { "python/v1d", ext.target_dir .. "/v1d" },
}