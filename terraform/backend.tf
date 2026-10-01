terraform {
  backend "gcs" {
    bucket = "anamnesis-tfstate-b7db2ae1"
    prefix = "terraform/state"
  }
}