use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Try Docker path first, then local development path
    let (proto_dir, protos) = if Path::new("proto/memory.proto").exists() {
        ("proto", vec!["proto/types.proto", "proto/memory.proto"]) // Docker build context
    } else {
        ("../proto", vec!["../proto/types.proto", "../proto/memory.proto"]) // Local development
    };

    tonic_build::configure()
        .compile_protos(&protos, &[proto_dir])?;
    Ok(())
}
