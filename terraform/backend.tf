terraform {
  backend "gcs" {
    bucket = "anamnesis-tfstate-gen-lang-client-0424267124"
    prefix = "terraform/state"
  }
}