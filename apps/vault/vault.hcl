# Vault server config for the rea showcase capture: file storage, plain HTTP inside the container, UI on.
# The host publishes this listener on 127.0.0.1:3303 only (see compose.yml).
ui            = true
disable_mlock = true
api_addr      = "http://127.0.0.1:3303"

storage "file" {
  path = "/vault/file"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true
}
