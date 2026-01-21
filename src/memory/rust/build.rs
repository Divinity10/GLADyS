use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Try Docker path first, then local development path
    let proto_path = if Path::new("proto/memory.proto").exists() {
        "proto/memory.proto" // Docker build context
    } else {
        "../proto/memory.proto" // Local development
    };

    tonic_build::compile_protos(proto_path)?;
    Ok(())
}
