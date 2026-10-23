# Product workflow browser path

The public Student 2 frontend calls its own `/multi-agent/workflow` and `/multi-agent/workflow/<id>/decision` paths. Its Flask server forwards these two paths to `API_BASE`, which is the internal Student 2 backend address in Compose and Azure. The internal `:5002` address is never constructed by the browser. Other Product APIs remain unchanged.

The current backend allows up to 600 seconds for a local Multi-Agent request. That setting reflects slow local model runs but has not been measured as a cloud requirement. Azure's mandatory profile disables Multi-Agent mode. Test the complete local workflow before changing the timeout.
