#pragma once

#include "network/apiclient.h"

// ApiService has been split into domain-specific API classes in src/network/:
//   ImagesApi   — image CRUD and fetch
//   AnalysisApi — analysis jobs and selection patches
//   ExportsApi  — export triggering and file download
//   AdminApi    — admin users, jobs, audit, impersonation
//
// This file is kept as an empty shell for backward-compatibility during migration.
// It will be removed once all callers have been updated to the domain classes.

class ApiService : public ApiClient
{
public:
    using ApiClient::ApiClient;
};
