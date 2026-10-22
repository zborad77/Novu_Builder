// VYGENEROVÁNO z src/contracts – NEUPRAVOVAT RUČNĚ.
// Přegenerování: npm run gen:contracts (kontrakty generuje backend: python -m scripts.export_contracts).

export interface paths {
    "/api/v1/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Root */
        get: operations["root_api_v1__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Audit Log */
        get: operations["get_audit_log_api_v1_admin_audit_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/companies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Companies */
        get: operations["list_companies_api_v1_admin_companies_get"];
        put?: never;
        /** Create Company */
        post: operations["create_company_api_v1_admin_companies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/companies/{company_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company */
        get: operations["get_company_api_v1_admin_companies__company_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Company */
        patch: operations["patch_company_api_v1_admin_companies__company_id__patch"];
        trace?: never;
    };
    "/api/v1/admin/impersonate/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Impersonate User
         * @description Issue a short-lived (15 min) access token scoped to the target user.
         *     The token carries impersonated_by=<admin_id> for audit trail.
         */
        post: operations["impersonate_user_api_v1_admin_impersonate__user_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List All Jobs */
        get: operations["list_all_jobs_api_v1_admin_jobs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Admin Job */
        get: operations["get_admin_job_api_v1_admin_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/jobs/{job_id}/reprocess": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Admin Reprocess Dead Letter Job */
        post: operations["admin_reprocess_dead_letter_job_api_v1_admin_jobs__job_id__reprocess_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Admin Retry Job */
        post: operations["admin_retry_job_api_v1_admin_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/logs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Recent Logs */
        get: operations["get_recent_logs_api_v1_admin_logs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/photos/{photo_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Admin Purge Photo
         * @description Permanently delete any tenant's photo (superadmin, audited as admin.image.purge).
         */
        post: operations["admin_purge_photo_api_v1_admin_photos__photo_id__purge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Users */
        get: operations["list_users_api_v1_admin_users_get"];
        put?: never;
        /** Create User */
        post: operations["create_user_api_v1_admin_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User */
        get: operations["get_user_api_v1_admin_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch User */
        patch: operations["patch_user_api_v1_admin_users__user_id__patch"];
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reset User Password */
        post: operations["reset_user_password_api_v1_admin_users__user_id__reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/alive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Alive
         * @description Legacy liveness alias; confirms the process is running.
         */
        get: operations["alive_api_v1_alive_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analysis-jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Analysis Job */
        get: operations["get_analysis_job_api_v1_analysis_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analysis-jobs/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Analysis Job */
        post: operations["cancel_analysis_job_api_v1_analysis_jobs__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analysis-jobs/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Analysis Job */
        post: operations["retry_analysis_job_api_v1_analysis_jobs__job_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/change-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change Password */
        post: operations["change_password_api_v1_auth_change_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/forgot-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Forgot Password
         * @description Self-service reset retired - no supported web client flow exists.
         */
        post: operations["forgot_password_api_v1_auth_forgot_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Password
         * @description Self-service reset retired - no supported web client flow exists.
         */
        post: operations["reset_password_api_v1_auth_reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Sessions */
        get: operations["list_sessions_api_v1_auth_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Revoke Session */
        delete: operations["revoke_session_api_v1_auth_sessions__session_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Cases */
        get: operations["list_cases_api_v1_cases_get"];
        put?: never;
        /** Create Case */
        post: operations["create_case_api_v1_cases_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Case */
        get: operations["get_case_api_v1_cases__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Case */
        patch: operations["patch_case_api_v1_cases__case_id__patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/activity/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * SSE stream — replay-safe real-time case activity updates
         * @description Open a Server-Sent Events stream for a single case.
         *
         *     Send Last-Event-ID on reconnect to replay any missed events.
         */
        get: operations["stream_case_activity_api_v1_cases__case_id__activity_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/analysis-jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Case Analysis Jobs */
        get: operations["list_case_analysis_jobs_api_v1_cases__case_id__analysis_jobs_get"];
        put?: never;
        /** Create Analysis Job */
        post: operations["create_analysis_job_api_v1_cases__case_id__analysis_jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/analysis-results/{result_id}/selection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Analysis Selection */
        patch: operations["patch_analysis_selection_api_v1_cases__case_id__analysis_results__result_id__selection_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/approve-proposal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Proposal
         * @description proposal_ready → quote_ready.  Manager signs off on the AI proposal.
         */
        post: operations["approve_proposal_api_v1_cases__case_id__approve_proposal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Archive Case
         * @description sent → archived.  Work completed / accepted.
         */
        post: operations["archive_case_api_v1_cases__case_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Case
         * @description any valid → cancelled.  Explicitly abandon the case.
         */
        post: operations["cancel_case_api_v1_cases__case_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/duplicate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Duplicate Case */
        post: operations["duplicate_case_api_v1_cases__case_id__duplicate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/estimates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Case Estimates */
        get: operations["list_case_estimates_api_v1_cases__case_id__estimates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/estimates/recalculate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Recalculate Case Estimates */
        post: operations["recalculate_case_estimates_api_v1_cases__case_id__estimates_recalculate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/exports/case-zip": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Case Zip */
        post: operations["create_case_zip_api_v1_cases__case_id__exports_case_zip_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/exports/proposal-docx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Proposal Docx */
        post: operations["create_proposal_docx_api_v1_cases__case_id__exports_proposal_docx_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/exports/quote-docx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Quote Docx */
        post: operations["create_quote_docx_api_v1_cases__case_id__exports_quote_docx_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/exports/quote-pdf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Quote Pdf */
        post: operations["create_quote_pdf_api_v1_cases__case_id__exports_quote_pdf_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/exports/report-pdf": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Report Pdf */
        post: operations["create_report_pdf_api_v1_cases__case_id__exports_report_pdf_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/final-proposal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Case Final Proposal */
        post: operations["create_case_final_proposal_api_v1_cases__case_id__final_proposal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Case Images */
        get: operations["list_case_images_api_v1_cases__case_id__images_get"];
        put?: never;
        /** Upload Case Images */
        post: operations["upload_case_images_api_v1_cases__case_id__images_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Case Image */
        delete: operations["delete_case_image_api_v1_cases__case_id__images__image_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}/analysis-reference": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Set Case Analysis Reference Image */
        patch: operations["set_case_analysis_reference_image_api_v1_cases__case_id__images__image_id__analysis_reference_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}/move": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Move Case Image */
        patch: operations["move_case_image_api_v1_cases__case_id__images__image_id__move_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}/primary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Set Case Primary Image */
        patch: operations["set_case_primary_image_api_v1_cases__case_id__images__image_id__primary_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}/purge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Purge Case Image
         * @description Permanently delete a photo and its derived files (company admin only).
         *
         *     Irreversible. Superadmins use POST /admin/photos/{image_id}/purge instead.
         */
        post: operations["purge_case_image_api_v1_cases__case_id__images__image_id__purge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/{image_id}/restore": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Restore Case Image */
        post: operations["restore_case_image_api_v1_cases__case_id__images__image_id__restore_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/images/deleted": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Deleted Case Images */
        get: operations["list_deleted_case_images_api_v1_cases__case_id__images_deleted_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/measurements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Or Update Measurement */
        post: operations["create_or_update_measurement_api_v1_cases__case_id__measurements_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/proposal-draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Case Proposal Draft */
        patch: operations["patch_case_proposal_draft_api_v1_cases__case_id__proposal_draft_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/return-to-draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Return Case To Draft
         * @description any valid → draft.  Unlock for edits or re-submission.
         */
        post: operations["return_case_to_draft_api_v1_cases__case_id__return_to_draft_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Case
         * @description quote_ready → sent.  Quote delivered to the client.
         *
         *     Guard: a final proposal must exist.
         */
        post: operations["send_case_api_v1_cases__case_id__send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/start-analysis": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Analysis
         * @description intake → analyzing.  Photos confirmed, analysis queued.
         */
        post: operations["start_analysis_api_v1_cases__case_id__start_analysis_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Submit Case
         * @description draft → intake.  Confirm the case is ready for processing.
         */
        post: operations["submit_case_api_v1_cases__case_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Case Timeline */
        get: operations["get_case_timeline_api_v1_cases__case_id__timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Project Work Items */
        get: operations["list_project_work_items_api_v1_cases__case_id__work_items_get"];
        put?: never;
        /** Create Project Work Item */
        post: operations["create_project_work_item_api_v1_cases__case_id__work_items_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items/{project_work_item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project Work Item Detail */
        get: operations["get_project_work_item_detail_api_v1_cases__case_id__work_items__project_work_item_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items/{project_work_item_id}/detections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Vision Detection */
        post: operations["create_vision_detection_api_v1_cases__case_id__work_items__project_work_item_id__detections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace Project Work Item Values */
        put: operations["replace_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Project Work Item Values */
        patch: operations["update_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_patch"];
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Project Work Item Values */
        post: operations["confirm_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values/merge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Merge Project Work Item Values */
        post: operations["merge_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_merge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cases/{case_id}/work-types/{work_type_code}/effective-configuration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project Work Item Effective Configuration */
        get: operations["get_project_work_item_effective_configuration_api_v1_cases__case_id__work_types__work_type_code__effective_configuration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/exports/{export_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Export */
        get: operations["get_export_api_v1_exports__export_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/exports/{export_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Export File */
        get: operations["download_export_file_api_v1_files_exports__export_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/images/{image_id}/{variant}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download Image File */
        get: operations["download_image_file_api_v1_files_images__image_id___variant__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Public health probe; reports truthful runtime integrity without internal counts.
         */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/images/{image_id}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Image Preview
         * @description Náhled fotky – streamuje se přímo (NC-007 kap. 6.3), žádná URL úložiště.
         *
         *     Dřív přesměrování (307) na podepsanou URL úložiště. Přesměrování na
         *     ``/files/images/{id}/preview`` by vyžadovalo druhý požadavek, u kterého
         *     klienti (Qt, gateway) nemusí znovu poslat ``Authorization``, a relativní
         *     ``/api/v1/...`` cesta není z webu přes ``/bff`` dosažitelná. Proto stejná
         *     kontrola firmy a stejné streamování jako ``/files/images/{id}/preview``;
         *     dokud náhled není hotový, vrací originál (jako dřív ``preview.url or url``).
         */
        get: operations["get_image_preview_api_v1_images__image_id__preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/internal/security-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ingest Security Events */
        post: operations["ingest_security_events_api_v1_internal_security_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/markers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Markers */
        get: operations["list_markers_api_v1_markers_get"];
        put?: never;
        /** Create Marker */
        post: operations["create_marker_api_v1_markers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/markers/{marker_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Marker */
        delete: operations["delete_marker_api_v1_markers__marker_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/material-catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Material Catalog */
        get: operations["list_material_catalog_api_v1_material_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/material-catalog/{material_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Material */
        patch: operations["patch_material_api_v1_material_catalog__material_id__patch"];
        trace?: never;
    };
    "/api/v1/material-catalog/{material_id}/supplier-prices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Supplier Prices */
        get: operations["list_supplier_prices_api_v1_material_catalog__material_id__supplier_prices_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/measurements/{measurement_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Measurement */
        patch: operations["patch_measurement_api_v1_measurements__measurement_id__patch"];
        trace?: never;
    };
    "/api/v1/measurements/{measurement_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Measurement */
        post: operations["confirm_measurement_api_v1_measurements__measurement_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit a new offer request (idempotent by idempotency_key) */
        post: operations["submit_offer_request_api_v1_offer_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get full offer request detail */
        get: operations["get_offer_request_api_v1_offer_requests__offer_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Operator: approve an offer in needs_review status */
        patch: operations["approve_offer_api_v1_offer_requests__offer_id__patch"];
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel a non-terminal offer request */
        post: operations["cancel_offer_request_api_v1_offer_requests__offer_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * SSE stream — replay-safe real-time offer status updates
         * @description Open a Server-Sent Events stream for a single offer request.
         *
         *     Send Last-Event-ID on reconnect to replay any missed events.
         */
        get: operations["stream_offer_events_api_v1_offer_requests__offer_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}/more-info": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit additional information when AI requested more data */
        post: operations["submit_more_info_api_v1_offer_requests__offer_id__more_info_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}/result": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Retrieve AI-generated offer result (only available in needs_review or completed) */
        get: operations["get_offer_result_api_v1_offer_requests__offer_id__result_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/offer-requests/{offer_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Lightweight status polling (preferred for Qt polling loop) */
        get: operations["get_offer_status_api_v1_offer_requests__offer_id__status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Org Users */
        get: operations["list_org_users_api_v1_org_users_get"];
        put?: never;
        /** Create Org User */
        post: operations["create_org_user_api_v1_org_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/org/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Org User */
        get: operations["get_org_user_api_v1_org_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Org User */
        patch: operations["patch_org_user_api_v1_org_users__user_id__patch"];
        trace?: never;
    };
    "/api/v1/org/users/{user_id}/reset-password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reset Org User Password */
        post: operations["reset_org_user_password_api_v1_org_users__user_id__reset_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pricebooks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pricebooks */
        get: operations["list_pricebooks_api_v1_pricebooks_get"];
        put?: never;
        /** Create Pricebook */
        post: operations["create_pricebook_api_v1_pricebooks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/pricebooks/{pricebook_id}/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pricebook Items */
        get: operations["list_pricebook_items_api_v1_pricebooks__pricebook_id__items_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Ready
         * @description Public readiness probe; returns ready only when traffic can be served safely.
         */
        get: operations["ready_api_v1_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ready/processing": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Ready Processing
         * @description Readiness for background-job processing, separate from API/read readiness.
         */
        get: operations["ready_processing_api_v1_ready_processing_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/suppliers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Suppliers */
        get: operations["list_suppliers_api_v1_suppliers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/suppliers/{supplier_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch Supplier */
        patch: operations["patch_supplier_api_v1_suppliers__supplier_id__patch"];
        trace?: never;
    };
    "/api/v1/work-catalog/catalog/categories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Catalog Categories */
        get: operations["list_catalog_categories_api_v1_work_catalog_catalog_categories_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/catalog/grouped": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Catalog Grouped */
        get: operations["list_catalog_grouped_api_v1_work_catalog_catalog_grouped_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/catalog/work-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Catalog Work Types */
        get: operations["list_catalog_work_types_api_v1_work_catalog_catalog_work_types_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/catalog/work-types/{work_type_code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Catalog Work Type Detail */
        get: operations["get_catalog_work_type_detail_api_v1_work_catalog_catalog_work_types__work_type_code__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/catalog/work-types/{work_type_code}/parameters/{parameter_code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Parameter Schema Detail */
        get: operations["get_parameter_schema_detail_api_v1_work_catalog_catalog_work_types__work_type_code__parameters__parameter_code__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/work-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Effective Work Types */
        get: operations["list_effective_work_types_api_v1_work_catalog_work_types_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/work-types/{work_type_code}/effective": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Effective Work Type */
        get: operations["get_effective_work_type_api_v1_work_catalog_work_types__work_type_code__effective_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/work-catalog/work-types/{work_type_code}/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upsert Tenant Work Type Setting */
        put: operations["upsert_tenant_work_type_setting_api_v1_work_catalog_work_types__work_type_code__settings_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/mock-storage/{file_path}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Serve Storage File */
        get: operations["serve_storage_file_mock_storage__file_path__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AdminUserCreate */
        AdminUserCreate: {
            /** Email */
            email: string;
            /** Fullname */
            fullName: string;
            /**
             * Isactive
             * @default true
             */
            isActive: boolean;
            /** Organizationid */
            organizationId: string;
            /** Password */
            password: string;
            /**
             * Role
             * @default technician
             * @enum {string}
             */
            role: "admin" | "manager" | "technician";
        };
        /** AdminUserListResponse */
        AdminUserListResponse: {
            /** Hasmore */
            hasMore: boolean;
            /** Items */
            items: components["schemas"]["AdminUserRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** AdminUserPatch */
        AdminUserPatch: {
            /** Fullname */
            fullName?: string | null;
            /** Isactive */
            isActive?: boolean | null;
            /** Password */
            password?: string | null;
            /** Role */
            role?: ("admin" | "manager" | "technician") | null;
        };
        /** AdminUserRead */
        AdminUserRead: {
            /** Createdat */
            createdAt?: string | null;
            /** Email */
            email: string;
            /** Fullname */
            fullName: string;
            /** Id */
            id: string;
            /** Isactive */
            isActive: boolean;
            /** Issuperadmin */
            isSuperAdmin: boolean;
            /** Organizationid */
            organizationId: string;
            /** Organizationname */
            organizationName?: string | null;
            /** Role */
            role: string;
        };
        /** AnalysisJobCreateRequest */
        AnalysisJobCreateRequest: {
            /** Worktypecode */
            workTypeCode?: string | null;
        };
        /** AnalysisProfileConfidenceThresholdRead */
        AnalysisProfileConfidenceThresholdRead: {
            /** Actionbelowthreshold */
            actionBelowThreshold: string;
            /** Attributecode */
            attributeCode: string;
            /** Minconfidence */
            minConfidence: number;
            /** Preferredconfidence */
            preferredConfidence: number;
            /** Sortorder */
            sortOrder: number;
            /** Targetobjectcode */
            targetObjectCode?: string | null;
        };
        /** AnalysisProfileExtractionRuleRead */
        AnalysisProfileExtractionRuleRead: {
            /** Attributecode */
            attributeCode: string;
            /** Datatype */
            dataType: string;
            /** Description */
            description?: string | null;
            /** Label */
            label: string;
            /** Manualreviewonmissing */
            manualReviewOnMissing: boolean;
            /** Required */
            required: boolean;
            /** Sortorder */
            sortOrder: number;
            /** Sourceobjectcode */
            sourceObjectCode: string;
            /** Targetparametercode */
            targetParameterCode: string;
            /** Unit */
            unit?: string | null;
        };
        /** AnalysisProfileFallbackBehaviorRead */
        AnalysisProfileFallbackBehaviorRead: {
            /** Instructions */
            instructions?: string | null;
            /** Mode */
            mode: string;
            /** Requiresmanualreview */
            requiresManualReview: boolean;
        };
        /** AnalysisProfileIgnoredObjectRead */
        AnalysisProfileIgnoredObjectRead: {
            /** Code */
            code: string;
            /** Label */
            label: string;
            /** Reason */
            reason?: string | null;
            /** Sortorder */
            sortOrder: number;
        };
        /** AnalysisProfileOutputMappingRead */
        AnalysisProfileOutputMappingRead: {
            /** Code */
            code: string;
            /** Required */
            required: boolean;
            /** Sortorder */
            sortOrder: number;
            /** Sourceattributecode */
            sourceAttributeCode: string;
            /** Targetentity */
            targetEntity: string;
            /** Targetfield */
            targetField: string;
            /** Targetparametercode */
            targetParameterCode?: string | null;
        };
        /** AnalysisProfileRead */
        AnalysisProfileRead: {
            /** Code */
            code: string;
            /** Confidencethreshold */
            confidenceThreshold?: number | null;
            /** Confidencethresholds */
            confidenceThresholds?: components["schemas"]["AnalysisProfileConfidenceThresholdRead"][];
            /** Extractionrules */
            extractionRules?: components["schemas"]["AnalysisProfileExtractionRuleRead"][];
            fallbackBehavior: components["schemas"]["AnalysisProfileFallbackBehaviorRead"];
            /** Ignoredobjects */
            ignoredObjects?: components["schemas"]["AnalysisProfileIgnoredObjectRead"][];
            /** Maxdetectionsperphoto */
            maxDetectionsPerPhoto: number;
            /** Name */
            name: string;
            /** Outputcontractversion */
            outputContractVersion: number;
            /** Outputmappings */
            outputMappings?: components["schemas"]["AnalysisProfileOutputMappingRead"][];
            /** Profileversion */
            profileVersion: number;
            /** Providerfamily */
            providerFamily: string;
            /** Scopecode */
            scopeCode: string;
            /** Scopedescription */
            scopeDescription?: string | null;
            /** Scopelabel */
            scopeLabel: string;
            /** Status */
            status: string;
            /** Targetobjects */
            targetObjects?: components["schemas"]["AnalysisProfileTargetObjectRead"][];
            /** Tasktype */
            taskType: string;
            /** Validationrules */
            validationRules?: components["schemas"]["AnalysisProfileValidationRuleRead"][];
        };
        /** AnalysisProfileTargetObjectRead */
        AnalysisProfileTargetObjectRead: {
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Isrequired */
            isRequired: boolean;
            /** Label */
            label: string;
            /** Objectrole */
            objectRole: string;
            /** Sortorder */
            sortOrder: number;
        };
        /** AnalysisProfileValidationRuleRead */
        AnalysisProfileValidationRuleRead: {
            /** Code */
            code: string;
            /** Maxnumbervalue */
            maxNumberValue?: number | null;
            /** Message */
            message: string;
            /** Minnumbervalue */
            minNumberValue?: number | null;
            /** Ruletype */
            ruleType: string;
            /** Severity */
            severity: string;
            /** Sortorder */
            sortOrder: number;
            /** Targetattributecode */
            targetAttributeCode?: string | null;
            /** Targetparametercode */
            targetParameterCode?: string | null;
        };
        /** AnalysisReferencePhotoResponse */
        AnalysisReferencePhotoResponse: {
            /** Message */
            message: string;
            photo: components["schemas"]["ProjectPhotoRead"];
        };
        /** AnalysisTriggerResponse */
        AnalysisTriggerResponse: {
            /** Analysisprofilecode */
            analysisProfileCode?: string | null;
            /** Analysisprofileversion */
            analysisProfileVersion?: number | null;
            /** Jobid */
            jobId: string;
            /** Modelname */
            modelName?: string | null;
            /** Modelversion */
            modelVersion?: string | null;
            /** Provider */
            provider?: string | null;
            /** Status */
            status: string;
            /** Worktypecode */
            workTypeCode?: string | null;
        };
        /** AuthSessionListResponse */
        AuthSessionListResponse: {
            /** Items */
            items: components["schemas"]["AuthSessionRead"][];
        };
        /** AuthSessionRead */
        AuthSessionRead: {
            /**
             * Accessexpiresat
             * Format: date-time
             */
            accessExpiresAt: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Id */
            id: string;
            /**
             * Iscurrent
             * @default false
             */
            isCurrent: boolean;
            /**
             * Refreshexpiresat
             * Format: date-time
             */
            refreshExpiresAt: string;
            /** Revokedat */
            revokedAt?: string | null;
        };
        /** AuthUserRead */
        AuthUserRead: {
            /** Email */
            email: string;
            /** Fullname */
            fullName: string;
            /** Id */
            id: string;
            /** Impersonatedby */
            impersonatedBy?: string | null;
            /** Isactive */
            isActive: boolean;
            /**
             * Issuperadmin
             * @default false
             */
            isSuperAdmin: boolean;
            /** Organizationid */
            organizationId: string;
            /** Role */
            role: string;
        };
        /**
         * CaseActionRequest
         * @description Optional body for explicit case action endpoints (submit, cancel, etc.).
         */
        CaseActionRequest: {
            /** Reason */
            reason?: string | null;
        };
        /** CatalogCategoryListItemRead */
        CatalogCategoryListItemRead: {
            /**
             * Activeworktypecount
             * @default 0
             */
            activeWorkTypeCount: number;
            /** Catalogversion */
            catalogVersion: number;
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
            /** Name Cs */
            name_cs?: string | null;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
            /**
             * Totalworktypecount
             * @default 0
             */
            totalWorkTypeCount: number;
        };
        /** CatalogCategoryListResponse */
        CatalogCategoryListResponse: {
            /** Items */
            items: components["schemas"]["CatalogCategoryListItemRead"][];
            /** Total */
            total: number;
        };
        /** CatalogGroupedCategoryRead */
        CatalogGroupedCategoryRead: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** Types */
            types?: components["schemas"]["CatalogGroupedWorkTypeRead"][];
        };
        /** CatalogGroupedResponse */
        CatalogGroupedResponse: {
            /** Items */
            items: components["schemas"]["CatalogGroupedCategoryRead"][];
            /** Total */
            total: number;
        };
        /** CatalogGroupedWorkTypeRead */
        CatalogGroupedWorkTypeRead: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** CatalogPricingProfileAdjustmentRuleRead */
        CatalogPricingProfileAdjustmentRuleRead: {
            /** Adjustmentvalue */
            adjustmentValue: number;
            /** Code */
            code: string;
            /** Conditionbooleanvalue */
            conditionBooleanValue?: boolean | null;
            /** Conditionnumbervalue */
            conditionNumberValue?: number | null;
            /** Conditionoperator */
            conditionOperator: string;
            /** Conditionoptioncode */
            conditionOptionCode?: string | null;
            /** Conditionsourcekey */
            conditionSourceKey: string;
            /** Conditionsourcetype */
            conditionSourceType: string;
            /** Conditiontextvalue */
            conditionTextValue?: string | null;
            /** Description */
            description?: string | null;
            /** Label */
            label: string;
            /** Operation */
            operation: string;
            /** Sortorder */
            sortOrder: number;
            /** Targetbaserulecode */
            targetBaseRuleCode?: string | null;
            /** Targetlinetype */
            targetLineType?: string | null;
            /** Targetscope */
            targetScope: string;
        };
        /** CatalogPricingProfileBaseRuleRead */
        CatalogPricingProfileBaseRuleRead: {
            /** Calculationmethod */
            calculationMethod: string;
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Label */
            label: string;
            /** Laborassumptioncode */
            laborAssumptionCode?: string | null;
            /** Linetype */
            lineType: string;
            /** Materialassumptioncode */
            materialAssumptionCode?: string | null;
            /** Quantitymultiplier */
            quantityMultiplier: number;
            /** Quantitysourcekey */
            quantitySourceKey?: string | null;
            /** Quantitysourcetype */
            quantitySourceType: string;
            /** Ratesource */
            rateSource: string;
            /** Ratevalue */
            rateValue?: number | null;
            /** Sortorder */
            sortOrder: number;
            /** Unit */
            unit: string;
        };
        /** CatalogPricingProfileLaborAssumptionRead */
        CatalogPricingProfileLaborAssumptionRead: {
            /** Code */
            code: string;
            /** Crewsize */
            crewSize?: number | null;
            /** Description */
            description?: string | null;
            /** Hoursperunit */
            hoursPerUnit: number;
            /** Label */
            label: string;
            /** Quantitysourcekey */
            quantitySourceKey?: string | null;
            /** Quantitysourcetype */
            quantitySourceType: string;
            /** Sortorder */
            sortOrder: number;
        };
        /** CatalogPricingProfileMaterialAssumptionRead */
        CatalogPricingProfileMaterialAssumptionRead: {
            /** Code */
            code: string;
            /** Defaultunitcost */
            defaultUnitCost?: number | null;
            /** Description */
            description?: string | null;
            /** Label */
            label: string;
            /** Quantityperunit */
            quantityPerUnit: number;
            /** Quantitysourcekey */
            quantitySourceKey?: string | null;
            /** Quantitysourcetype */
            quantitySourceType: string;
            /** Sortorder */
            sortOrder: number;
            /** Unit */
            unit: string;
            /** Wastefactorpct */
            wasteFactorPct?: number | null;
        };
        /** CatalogPricingProfileRead */
        CatalogPricingProfileRead: {
            /** Adjustmentrules */
            adjustmentRules?: components["schemas"]["CatalogPricingProfileAdjustmentRuleRead"][];
            /** Baserules */
            baseRules?: components["schemas"]["CatalogPricingProfileBaseRuleRead"][];
            /** Code */
            code: string;
            /** Currency */
            currency: string;
            /** Defaultmarginpct */
            defaultMarginPct?: number | null;
            /** Defaultmarkuppct */
            defaultMarkupPct?: number | null;
            /** Laborassumptions */
            laborAssumptions?: components["schemas"]["CatalogPricingProfileLaborAssumptionRead"][];
            /** Laborratesource */
            laborRateSource: string;
            /** Materialassumptions */
            materialAssumptions?: components["schemas"]["CatalogPricingProfileMaterialAssumptionRead"][];
            /** Materialpricingsource */
            materialPricingSource: string;
            /** Minjobprice */
            minJobPrice?: number | null;
            /** Name */
            name: string;
            /** Pricingbasis */
            pricingBasis: string;
            /** Pricingstrategy */
            pricingStrategy: string;
            /** Profileversion */
            profileVersion: number;
            /** Requiredinputs */
            requiredInputs?: components["schemas"]["CatalogPricingProfileRequiredInputRead"][];
            /** Status */
            status: string;
        };
        /** CatalogPricingProfileRequiredInputRead */
        CatalogPricingProfileRequiredInputRead: {
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Label */
            label: string;
            /** Required */
            required: boolean;
            /** Sortorder */
            sortOrder: number;
            /** Sourcekey */
            sourceKey: string;
            /** Sourcetype */
            sourceType: string;
        };
        /** CatalogWorkTypeDetailRead */
        CatalogWorkTypeDetailRead: {
            analysisProfile?: components["schemas"]["AnalysisProfileRead"] | null;
            catalogPricingProfile?: components["schemas"]["CatalogPricingProfileRead"] | null;
            category: components["schemas"]["WorkCategoryRead"];
            /** Code */
            code: string;
            /** Defaultunit */
            defaultUnit: string;
            /** Description */
            description?: string | null;
            /** Measurementkind */
            measurementKind: string;
            /** Name */
            name: string;
            /** Parameters */
            parameters?: components["schemas"]["WorkTypeParameterRead"][];
            /** Parametersections */
            parameterSections?: components["schemas"]["WorkTypeParameterSectionRead"][];
            phaseBinding: components["schemas"]["WorkTypePhaseBindingRead"];
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
            /** State */
            state: string;
            /** Supportspricing */
            supportsPricing: boolean;
            /** Supportsvision */
            supportsVision: boolean;
            /** Worktypeversion */
            workTypeVersion: number;
        };
        /** CatalogWorkTypeListItemRead */
        CatalogWorkTypeListItemRead: {
            category: components["schemas"]["WorkCategoryRead"];
            /** Code */
            code: string;
            /** Defaultunit */
            defaultUnit: string;
            /** Description */
            description?: string | null;
            /** Measurementkind */
            measurementKind: string;
            /** Name */
            name: string;
            /** Parametercount */
            parameterCount: number;
            phaseBinding: components["schemas"]["WorkTypePhaseBindingRead"];
            /** Requiredparametercount */
            requiredParameterCount: number;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
            /** State */
            state: string;
            /** Supportspricing */
            supportsPricing: boolean;
            /** Supportsvision */
            supportsVision: boolean;
            /** Worktypeversion */
            workTypeVersion: number;
        };
        /** CatalogWorkTypeListResponse */
        CatalogWorkTypeListResponse: {
            /** Items */
            items: components["schemas"]["CatalogWorkTypeListItemRead"][];
            /** Total */
            total: number;
        };
        /** ChangePasswordRequest */
        ChangePasswordRequest: {
            /** Currentpassword */
            currentPassword: string;
            /** Newpassword */
            newPassword: string;
        };
        /** ChangePasswordResponse */
        ChangePasswordResponse: {
            /** Message */
            message: string;
        };
        /** CompanyCreate */
        CompanyCreate: {
            /**
             * Defaultcurrency
             * @default CZK
             */
            defaultCurrency: string;
            /** Email */
            email?: string | null;
            /** Ico */
            ico?: string | null;
            /** Name */
            name: string;
            /** Phone */
            phone?: string | null;
        };
        /** CompanyListResponse */
        CompanyListResponse: {
            /** Hasmore */
            hasMore: boolean;
            /** Items */
            items: components["schemas"]["CompanyRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Total */
            total: number;
        };
        /** CompanyPatch */
        CompanyPatch: {
            /** Defaultcurrency */
            defaultCurrency?: string | null;
            /** Email */
            email?: string | null;
            /** Ico */
            ico?: string | null;
            /** Name */
            name?: string | null;
            /** Phone */
            phone?: string | null;
        };
        /** CompanyRead */
        CompanyRead: {
            /** Createdat */
            createdAt?: string | null;
            /** Defaultcurrency */
            defaultCurrency: string;
            /** Email */
            email: string | null;
            /** Ico */
            ico: string | null;
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Phone */
            phone: string | null;
            /**
             * Usercount
             * @default 0
             */
            userCount: number;
        };
        /** DeletedPhotoListResponse */
        DeletedPhotoListResponse: {
            /** Items */
            items: components["schemas"]["DeletedPhotoRead"][];
        };
        /**
         * DeletedPhotoRead
         * @description A soft-deleted photo that can still be restored.
         */
        DeletedPhotoRead: {
            /** Deletedat */
            deletedAt: string | null;
            /** Deletedbyuserid */
            deletedByUserId: string | null;
            /** Id */
            id: string;
            /** Originalfilename */
            originalFilename: string;
        };
        /** DeletePhotoResponse */
        DeletePhotoResponse: {
            /** Message */
            message: string;
        };
        /** EffectivePricingConfigurationRead */
        EffectivePricingConfigurationRead: {
            /** Catalogpricingprofilecode */
            catalogPricingProfileCode?: string | null;
            /** Catalogpricingprofileversion */
            catalogPricingProfileVersion?: number | null;
            /** Conditionparametercodes */
            conditionParameterCodes?: string[];
            /** Parameterinputcodes */
            parameterInputCodes?: string[];
            /** Quantityparametercodes */
            quantityParameterCodes?: string[];
            /** Requiredinputcodes */
            requiredInputCodes?: string[];
            /** Supported */
            supported: boolean;
            /** Tenantpricingprofileid */
            tenantPricingProfileId?: string | null;
            /** Workitemfieldinputcodes */
            workItemFieldInputCodes?: string[];
        };
        /** EffectiveVisionConfigurationRead */
        EffectiveVisionConfigurationRead: {
            /** Analysisprofilecode */
            analysisProfileCode?: string | null;
            /** Analysisprofileversion */
            analysisProfileVersion?: number | null;
            /** Extractableparametercodes */
            extractableParameterCodes?: string[];
            /**
             * Fallbackrequiresmanualreview
             * @default false
             */
            fallbackRequiresManualReview: boolean;
            /** Outputparametercodes */
            outputParameterCodes?: string[];
            /** Supported */
            supported: boolean;
            /** Tasktype */
            taskType?: string | null;
        };
        /** EffectiveWorkTypeListResponse */
        EffectiveWorkTypeListResponse: {
            /** Items */
            items: components["schemas"]["EffectiveWorkTypeRead"][];
            /** Total */
            total: number;
        };
        /** EffectiveWorkTypeRead */
        EffectiveWorkTypeRead: {
            analysisProfile?: components["schemas"]["AnalysisProfileRead"] | null;
            catalogPricingProfile?: components["schemas"]["CatalogPricingProfileRead"] | null;
            category: components["schemas"]["WorkCategoryRead"];
            /** Code */
            code: string;
            /** Defaultunit */
            defaultUnit: string;
            /** Description */
            description?: string | null;
            /** Effectivedisplayname */
            effectiveDisplayName: string;
            /** Extraparameters */
            extraParameters?: components["schemas"]["TenantWorkTypeExtraParameterRead"][];
            /** Isenabled */
            isEnabled: boolean;
            /** Measurementkind */
            measurementKind: string;
            /** Name */
            name: string;
            /** Parameteroverrides */
            parameterOverrides?: components["schemas"]["TenantWorkTypeParameterOverrideRead"][];
            /** Parameters */
            parameters?: components["schemas"]["WorkTypeParameterRead"][];
            /** Parametersections */
            parameterSections?: components["schemas"]["WorkTypeParameterSectionRead"][];
            phaseBinding: components["schemas"]["WorkTypePhaseBindingRead"];
            /** Settingversion */
            settingVersion?: number | null;
            /** Slug */
            slug: string;
            /** State */
            state: string;
            /** Tenantpricingprofileid */
            tenantPricingProfileId?: string | null;
            tenantSetting?: components["schemas"]["TenantWorkTypeSettingRead"] | null;
            /** Worktypeversion */
            workTypeVersion: number;
        };
        /** ExportCreateResponse */
        ExportCreateResponse: {
            /** Exportid */
            exportId: string;
            /** Status */
            status: string;
        };
        /** ExportRead */
        ExportRead: {
            /** Caseid */
            caseId: string;
            /** Completedat */
            completedAt?: string | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Downloadurl */
            downloadUrl?: string | null;
            /** Expiresat */
            expiresAt?: string | null;
            /** Exporttype */
            exportType: string;
            /** Filename */
            fileName: string;
            /** Id */
            id: string;
            /** Status */
            status: string;
            /** Storagekey */
            storageKey?: string | null;
        };
        /** ForgotPasswordResponse */
        ForgotPasswordResponse: {
            /** Message */
            message: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImpersonateResponse */
        ImpersonateResponse: {
            /** Accesstoken */
            accessToken: string;
            /**
             * Expiresinminutes
             * @default 15
             */
            expiresInMinutes: number;
            /** Orgid */
            orgId: string;
            /** Role */
            role: string;
            /** Useremail */
            userEmail: string;
            /** Userfullname */
            userFullName: string;
            /** Userid */
            userId: string;
        };
        /** LoginRequest */
        LoginRequest: {
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** LoginResponse */
        LoginResponse: {
            /** Accesstoken */
            accessToken: string;
            /** Refreshtoken */
            refreshToken: string;
            /** Sessionid */
            sessionId?: string | null;
            /**
             * Tokentype
             * @default bearer
             */
            tokenType: string;
            user: components["schemas"]["AuthUserRead"];
        };
        /** LogoutRequest */
        LogoutRequest: {
            /** Refreshtoken */
            refreshToken: string;
        };
        /** LogoutResponse */
        LogoutResponse: {
            /** Message */
            message: string;
        };
        /** MarkerCreate */
        MarkerCreate: {
            /** Caseid */
            caseId: string;
            /** Height */
            height?: number | null;
            /** Imageid */
            imageId?: string | null;
            /** Label */
            label: string;
            /**
             * Markertype
             * @enum {string}
             */
            markerType: "defect" | "note" | "ai_detection" | "measurement";
            /** Severity */
            severity?: string | null;
            /** Width */
            width?: number | null;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /** MarkerDeleteResponse */
        MarkerDeleteResponse: {
            /** Message */
            message: string;
        };
        /** MarkerListResponse */
        MarkerListResponse: {
            /** Items */
            items: components["schemas"]["MarkerRead"][];
        };
        /** MarkerRead */
        MarkerRead: {
            /** Caseid */
            caseId: string;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /** Createdby */
            createdBy?: string | null;
            /** Height */
            height?: number | null;
            /** Id */
            id: string;
            /** Imageid */
            imageId?: string | null;
            /** Label */
            label: string;
            /** Markersource */
            markerSource: string;
            /** Markertype */
            markerType: string;
            /** Severity */
            severity?: string | null;
            /** Width */
            width?: number | null;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /** MaterialCatalogPatch */
        MaterialCatalogPatch: {
            /** Defaultsupplierid */
            defaultSupplierId?: string | null;
            /** Defaultunitprice */
            defaultUnitPrice: number;
            /** Notes */
            notes?: string | null;
        };
        /** MeasurementPolygonPoint */
        MeasurementPolygonPoint: {
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /** MeasurementRead */
        MeasurementRead: {
            /** Aiareasqm */
            aiAreaSqm?: number | null;
            /** Caseid */
            caseId: string;
            /** Confirmed */
            confirmed: boolean;
            /** Createdat */
            createdAt?: string | null;
            /** Finalareasource */
            finalAreaSource: string;
            /** Id */
            id: string;
            /** Manualareasqm */
            manualAreaSqm?: number | null;
            /** Referenceimageid */
            referenceImageId?: string | null;
            /** Selectedrepairpolygon */
            selectedRepairPolygon?: components["schemas"]["MeasurementPolygonPoint"][] | null;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** MeasurementUpsert */
        MeasurementUpsert: {
            /** Finalareasource */
            finalAreaSource?: string | null;
            /** Manualareasqm */
            manualAreaSqm?: number | null;
            /** Referenceimageid */
            referenceImageId?: string | null;
            /** Selectedrepairpolygon */
            selectedRepairPolygon?: components["schemas"]["MeasurementPolygonPoint"][] | null;
        };
        /** MoreInfoSubmit */
        MoreInfoSubmit: {
            /** Additional Parameters */
            additional_parameters?: {
                [key: string]: unknown;
            };
            /** Additional Photo Ids */
            additional_photo_ids?: string[];
        };
        /** OfferApprove */
        OfferApprove: {
            /** Action */
            action: string;
        };
        /** OfferRequestCreate */
        OfferRequestCreate: {
            /**
             * Auto Review Bypass
             * @default false
             */
            auto_review_bypass: boolean;
            /**
             * Auto Send
             * @default false
             */
            auto_send: boolean;
            /** Client Id */
            client_id?: string | null;
            /** Client Version */
            client_version?: string | null;
            /** Idempotency Key */
            idempotency_key: string;
            /** Parameters */
            parameters?: {
                [key: string]: unknown;
            };
            /** Photo Ids */
            photo_ids?: string[];
            /** Title */
            title: string;
            /** Work Type Code */
            work_type_code: string;
        };
        /** OfferRequestRead */
        OfferRequestRead: {
            /** Auto Review Bypass */
            auto_review_bypass: boolean;
            /** Auto Send */
            auto_send: boolean;
            /** Cancelled At */
            cancelled_at: string | null;
            /** Client Id */
            client_id: string | null;
            /** Client Version */
            client_version: string | null;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Needs More Info Payload */
            needs_more_info_payload: {
                [key: string]: unknown;
            } | null;
            /** Organization Id */
            organization_id: string;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Photo Ids */
            photo_ids: string[];
            /** Result Ready At */
            result_ready_at: string | null;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Work Type Code */
            work_type_code: string;
        };
        /** OfferResultRead */
        OfferResultRead: {
            /** Completed At */
            completed_at: string | null;
            /** Id */
            id: string;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Result Ready At */
            result_ready_at: string | null;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /** Work Type Code */
            work_type_code: string;
        };
        /** OfferStatusRead */
        OfferStatusRead: {
            /** Id */
            id: string;
            /** Needs More Info Payload */
            needs_more_info_payload: {
                [key: string]: unknown;
            } | null;
            /** Result Ready At */
            result_ready_at: string | null;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** OfferSubmitResponse */
        OfferSubmitResponse: {
            /**
             * Created
             * @description True if a new offer was created (201), False if idempotent replay (200).
             */
            created: boolean;
            /** Id */
            id: string;
            /** Status */
            status: string;
        };
        /** OrgUserCreate */
        OrgUserCreate: {
            /** Email */
            email: string;
            /** Fullname */
            fullName: string;
            /**
             * Isactive
             * @default true
             */
            isActive: boolean;
            /** Password */
            password: string;
            /**
             * Role
             * @default technician
             * @enum {string}
             */
            role: "admin" | "manager" | "technician";
        };
        /** OrgUserPasswordReset */
        OrgUserPasswordReset: {
            /** Password */
            password: string;
        };
        /** OrgUserPatch */
        OrgUserPatch: {
            /** Fullname */
            fullName?: string | null;
            /** Isactive */
            isActive?: boolean | null;
            /** Role */
            role?: ("admin" | "manager" | "technician") | null;
        };
        /** ParameterSchemaAnalysisBindingRead */
        ParameterSchemaAnalysisBindingRead: {
            /** Attributecode */
            attributeCode?: string | null;
            /** Bindingcode */
            bindingCode: string;
            /** Bindingtype */
            bindingType: string;
            /** Required */
            required?: boolean | null;
            /** Targetentity */
            targetEntity?: string | null;
        };
        /** ParameterSchemaDetailRead */
        ParameterSchemaDetailRead: {
            /** Analysisbindings */
            analysisBindings?: components["schemas"]["ParameterSchemaAnalysisBindingRead"][];
            category: components["schemas"]["WorkCategoryRead"];
            parameter: components["schemas"]["WorkTypeParameterRead"];
            /** Pricingbindings */
            pricingBindings?: components["schemas"]["ParameterSchemaPricingBindingRead"][];
            /** Supportspricinginput */
            supportsPricingInput: boolean;
            /** Supportsvisionpopulation */
            supportsVisionPopulation: boolean;
            /** Worktypecode */
            workTypeCode: string;
            /** Worktypename */
            workTypeName: string;
        };
        /** ParameterSchemaPricingBindingRead */
        ParameterSchemaPricingBindingRead: {
            /** Bindingcode */
            bindingCode: string;
            /** Bindingtype */
            bindingType: string;
            /** Linetype */
            lineType?: string | null;
            /** Required */
            required?: boolean | null;
            /** Sourcekey */
            sourceKey?: string | null;
            /** Sourcetype */
            sourceType: string;
        };
        /** PhotoListMeta */
        PhotoListMeta: {
            /** Analysisreferencephotoid */
            analysisReferencePhotoId?: string | null;
            /** Derivativestrategy */
            derivativeStrategy: {
                [key: string]: string;
            };
            /** Hasminimumcount */
            hasMinimumCount: boolean;
            /** Minimumrecommendedcount */
            minimumRecommendedCount: number;
            /** Primaryphotoid */
            primaryPhotoId?: string | null;
        };
        /** PhotoListResponse */
        PhotoListResponse: {
            /** Items */
            items: components["schemas"]["ProjectPhotoRead"][];
            meta: components["schemas"]["PhotoListMeta"];
        };
        /** PhotoMoveRequest */
        PhotoMoveRequest: {
            /**
             * Direction
             * @enum {string}
             */
            direction: "up" | "down";
        };
        /** PhotoUploadResponse */
        PhotoUploadResponse: {
            /** Uploaded */
            uploaded: components["schemas"]["UploadedPhotoPayload"][];
        };
        /** PhotoVariant */
        PhotoVariant: {
            /** Filesize */
            fileSize?: number | null;
            /** Height */
            height?: number | null;
            /** Storagekey */
            storageKey?: string | null;
            /** Url */
            url?: string | null;
            /** Width */
            width?: number | null;
        };
        /** PhotoVariants */
        PhotoVariants: {
            aiInput: components["schemas"]["PhotoVariant"];
            original: components["schemas"]["PhotoVariant"];
            preview: components["schemas"]["PhotoVariant"];
        };
        /** PricebookCreate */
        PricebookCreate: {
            /**
             * Currency
             * @default CZK
             */
            currency: string;
            /** Dailyrate */
            dailyRate: number;
            /** Hourlyrate */
            hourlyRate: number;
            /**
             * Isdefault
             * @default false
             */
            isDefault: boolean;
            /** Laborhourspersqm */
            laborHoursPerSqm: number;
            /** Name */
            name: string;
            /**
             * Vatpct
             * @default 21
             */
            vatPct: number;
        };
        /** PricebookItemRead */
        PricebookItemRead: {
            /** Category */
            category?: string | null;
            /** Defaultsupplierid */
            defaultSupplierId?: string | null;
            /** Defaultunitprice */
            defaultUnitPrice: number;
            /** Id */
            id: string;
            /** Isactive */
            isActive: boolean;
            /** Materialcatalogid */
            materialCatalogId: string;
            /** Name */
            name: string;
            /** Normpersqm */
            normPerSqm: number;
            /** Notes */
            notes?: string | null;
            /** Unit */
            unit: string;
        };
        /** PricebookListResponse */
        PricebookListResponse: {
            /** Items */
            items: components["schemas"]["PricebookRead"][];
        };
        /** PricebookRead */
        PricebookRead: {
            /** Createdat */
            createdAt?: string | null;
            /** Currency */
            currency: string;
            /** Dailyrate */
            dailyRate: number;
            /** Hourlyrate */
            hourlyRate: number;
            /** Id */
            id: string;
            /** Isdefault */
            isDefault: boolean;
            /** Laborhourspersqm */
            laborHoursPerSqm: number;
            /** Name */
            name: string;
            /** Organizationid */
            organizationId: string;
            /** Updatedat */
            updatedAt?: string | null;
            /** Vatpct */
            vatPct: number;
        };
        /** PrimaryPhotoResponse */
        PrimaryPhotoResponse: {
            /** Message */
            message: string;
            photo: components["schemas"]["ProjectPhotoRead"];
        };
        /** ProjectClient */
        ProjectClient: {
            /** Companyname */
            companyName?: string | null;
            /** Email */
            email?: string | null;
            /** Fullname */
            fullName: string;
            /** Id */
            id: string;
            /** Phone */
            phone?: string | null;
        };
        /** ProjectCreate */
        ProjectCreate: {
            /** Addresslabel */
            addressLabel?: string | null;
            /** Clientid */
            clientId?: string | null;
            /** Description */
            description?: string | null;
            /** Locationlat */
            locationLat?: number | null;
            /** Locationlng */
            locationLng?: number | null;
            /** Propertytype */
            propertyType?: string | null;
            /** Repairscope */
            repairScope?: string | null;
            /**
             * Source
             * @default mobile
             */
            source: string;
            /** Title */
            title: string;
        };
        /** ProjectCreateResponse */
        ProjectCreateResponse: {
            /** Id */
            id: string;
            /** Status */
            status: string;
        };
        /** ProjectDetail */
        ProjectDetail: {
            /** Availabletransitions */
            availableTransitions?: components["schemas"]["TransitionRead"][];
            client?: components["schemas"]["ProjectClient"] | null;
            /** Createdat */
            createdAt?: string | null;
            /** Description */
            description?: string | null;
            finalProposal?: components["schemas"]["ProjectFinalProposal"] | null;
            /** Id */
            id: string;
            /**
             * Isreferencedataset
             * @default false
             */
            isReferenceDataset: boolean;
            /** Latestanalysis */
            latestAnalysis?: {
                [key: string]: unknown;
            } | null;
            location: components["schemas"]["ProjectLocation"];
            /** Photos */
            photos?: unknown[];
            /** Propertytype */
            propertyType?: string | null;
            proposalDraft?: components["schemas"]["ProjectProposalDraft"] | null;
            /** Quotevariants */
            quoteVariants?: unknown[];
            referenceExpectations?: components["schemas"]["ProjectReferenceExpectations"] | null;
            /** Repairscope */
            repairScope?: string | null;
            /**
             * Source
             * @default mobile
             */
            source: string;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /** Updatedat */
            updatedAt?: string | null;
            workflowStatus?: components["schemas"]["ProjectWorkflowStatusSummary"] | null;
        };
        /** ProjectDuplicateRequest */
        ProjectDuplicateRequest: {
            /**
             * Mode
             * @default copy
             * @enum {string}
             */
            mode: "copy" | "variant";
            /** Title */
            title?: string | null;
        };
        /** ProjectFinalProposal */
        ProjectFinalProposal: {
            /** Analysisresultid */
            analysisResultId?: string | null;
            /** Createdat */
            createdAt?: string | null;
            /**
             * Currency
             * @default CZK
             */
            currency: string;
            /** Draftversion */
            draftVersion: number;
            /** Id */
            id: string;
            /** Inputversions */
            inputVersions?: {
                [key: string]: unknown;
            } | null;
            /** Sections */
            sections?: components["schemas"]["ProposalDraftSection"][];
            /** Status */
            status: string;
            /** Subject */
            subject?: string | null;
            /** Summary */
            summary?: string | null;
            /** Totalprice */
            totalPrice?: number | null;
        };
        /** ProjectListResponse */
        ProjectListResponse: {
            /** Items */
            items: components["schemas"]["ProjectSummary"][];
            /** Next Cursor */
            next_cursor?: string | null;
            /** Total */
            total: number;
        };
        /** ProjectLocation */
        ProjectLocation: {
            /** Addresslabel */
            addressLabel?: string | null;
            /** Lat */
            lat?: number | null;
            /** Lng */
            lng?: number | null;
        };
        /** ProjectPatch */
        ProjectPatch: {
            /** Addresslabel */
            addressLabel?: string | null;
            /** Clientid */
            clientId?: string | null;
            /** Description */
            description?: string | null;
            /** Locationlat */
            locationLat?: number | null;
            /** Locationlng */
            locationLng?: number | null;
            /** Propertytype */
            propertyType?: string | null;
            /** Repairscope */
            repairScope?: string | null;
            /** Title */
            title?: string | null;
        };
        /** ProjectPhotoRead */
        ProjectPhotoRead: {
            /** Candelete */
            canDelete?: boolean | null;
            /** Exiflat */
            exifLat?: number | null;
            /** Exiflng */
            exifLng?: number | null;
            /** Filesize */
            fileSize: number;
            /** Height */
            height?: number | null;
            /** Id */
            id: string;
            /** Isanalysisreference */
            isAnalysisReference: boolean;
            /** Isprimary */
            isPrimary: boolean;
            /** Mimetype */
            mimeType: string;
            /** Originalfilename */
            originalFilename: string;
            /** Processingstatus */
            processingStatus: string;
            /** Projectid */
            projectId: string;
            /** Sortorder */
            sortOrder: number;
            /** Storagekey */
            storageKey: string;
            /** Takenat */
            takenAt?: string | null;
            /** Uploadedbyuserid */
            uploadedByUserId?: string | null;
            /** Url */
            url: string;
            variants: components["schemas"]["PhotoVariants"];
            /** Width */
            width?: number | null;
        };
        /** ProjectProposalDraft */
        ProjectProposalDraft: {
            /** Amortization */
            amortization?: number | null;
            /** Laborcost */
            laborCost?: number | null;
            /** Margin */
            margin?: number | null;
            /** Materialcost */
            materialCost?: number | null;
            /** Materials */
            materials?: components["schemas"]["ProposalDraftMaterial"][];
            /** Primaryphotoid */
            primaryPhotoId?: string | null;
            /**
             * Readyphotocount
             * @default 0
             */
            readyPhotoCount: number;
            /** Recommendedcompany */
            recommendedCompany?: string | null;
            /** Recommendedsupplier */
            recommendedSupplier?: string | null;
            /** Sections */
            sections?: components["schemas"]["ProposalDraftSection"][];
            /**
             * Sourcephotocount
             * @default 0
             */
            sourcePhotoCount: number;
            /** Status */
            status: string;
            /** Subject */
            subject?: string | null;
            /** Suggestedworkitems */
            suggestedWorkItems?: components["schemas"]["ProposalDraftWorkItem"][];
            /** Summary */
            summary?: string | null;
            /** Totalprice */
            totalPrice?: number | null;
            /** Transportcost */
            transportCost?: number | null;
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /** ProjectProposalDraftPatch */
        ProjectProposalDraftPatch: {
            /** Amortization */
            amortization?: number | null;
            /** Expectedversion */
            expectedVersion?: number | null;
            /** Laborcost */
            laborCost?: number | null;
            /** Margin */
            margin?: number | null;
            /** Materialcost */
            materialCost?: number | null;
            /** Recommendedcompany */
            recommendedCompany?: string | null;
            /** Recommendedsupplier */
            recommendedSupplier?: string | null;
            /** Subject */
            subject?: string | null;
            /** Summary */
            summary?: string | null;
            /** Transportcost */
            transportCost?: number | null;
        };
        /** ProjectReferenceExpectations */
        ProjectReferenceExpectations: {
            /** Expectedanalysisreferencefilename */
            expectedAnalysisReferenceFilename?: string | null;
            /** Expectedprimaryfilename */
            expectedPrimaryFilename?: string | null;
            /** Expectedscope */
            expectedScope?: string | null;
            /** Sourcepage */
            sourcePage?: string | null;
            /** Sourcerepo */
            sourceRepo?: string | null;
        };
        /** ProjectSummary */
        ProjectSummary: {
            /** Addresslabel */
            addressLabel?: string | null;
            /** Createdbyname */
            createdByName?: string | null;
            /** Estimatedareasqm */
            estimatedAreaSqm?: number | null;
            /** Id */
            id: string;
            /**
             * Isreferencedataset
             * @default false
             */
            isReferenceDataset: boolean;
            /** Latestquotetotal */
            latestQuoteTotal?: number | null;
            /**
             * Photocount
             * @default 0
             */
            photoCount: number;
            /** Propertytype */
            propertyType?: string | null;
            /** Repairscope */
            repairScope?: string | null;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** ProjectWorkflowPhotoReadiness */
        ProjectWorkflowPhotoReadiness: {
            /**
             * Hasanalysisreferencereadyphoto
             * @default false
             */
            hasAnalysisReferenceReadyPhoto: boolean;
            /**
             * Hasminimumrecommendedcount
             * @default false
             */
            hasMinimumRecommendedCount: boolean;
            /**
             * Hasprimaryreadyphoto
             * @default false
             */
            hasPrimaryReadyPhoto: boolean;
            /**
             * Minimumrecommendedcount
             * @default 3
             */
            minimumRecommendedCount: number;
            /**
             * Readyphotocount
             * @default 0
             */
            readyPhotoCount: number;
            /**
             * Totalphotocount
             * @default 0
             */
            totalPhotoCount: number;
        };
        /** ProjectWorkflowStatusSummary */
        ProjectWorkflowStatusSummary: {
            /** Analysisstatus */
            analysisStatus: string;
            /** Blockingreasons */
            blockingReasons?: string[];
            /**
             * Cancreatefinalproposal
             * @default false
             */
            canCreateFinalProposal: boolean;
            /**
             * Cansend
             * @default false
             */
            canSend: boolean;
            /** Draftstatus */
            draftStatus: string;
            /** Finalproposalstatus */
            finalProposalStatus?: string | null;
            photoReadiness: components["schemas"]["ProjectWorkflowPhotoReadiness"];
        };
        /** ProjectWorkItemCreate */
        ProjectWorkItemCreate: {
            /** Measuredquantity */
            measuredQuantity?: number | null;
            /** Measuredunit */
            measuredUnit?: string | null;
            /** Notes */
            notes?: string | null;
            /**
             * Sourcetype
             * @default manual
             */
            sourceType: string;
            /**
             * Status
             * @default resolved
             */
            status: string;
            /** Title */
            title?: string | null;
            /** Values */
            values?: components["schemas"]["ProjectWorkItemValueInput"][];
            /** Worktypecode */
            workTypeCode: string;
        };
        /** ProjectWorkItemDetailRead */
        ProjectWorkItemDetailRead: {
            effectiveConfiguration: components["schemas"]["ProjectWorkItemEffectiveConfigurationRead"];
            workflow: components["schemas"]["ProjectWorkItemWorkflowRead"];
            workItem: components["schemas"]["ProjectWorkItemRead"];
        };
        /** ProjectWorkItemEffectiveConfigurationRead */
        ProjectWorkItemEffectiveConfigurationRead: {
            /** Casestatus */
            caseStatus: string;
            /** Defaultedparametercodes */
            defaultedParameterCodes?: string[];
            effectiveWorkType: components["schemas"]["EffectiveWorkTypeRead"];
            pricing: components["schemas"]["EffectivePricingConfigurationRead"];
            /** Projectid */
            projectId: string;
            /** Requiredparametercodes */
            requiredParameterCodes?: string[];
            vision: components["schemas"]["EffectiveVisionConfigurationRead"];
            /** Worktypecode */
            workTypeCode: string;
        };
        /** ProjectWorkItemListResponse */
        ProjectWorkItemListResponse: {
            /** Items */
            items: components["schemas"]["ProjectWorkItemRead"][];
            /** Total */
            total: number;
        };
        /** ProjectWorkItemRead */
        ProjectWorkItemRead: {
            /** Analysisprofilecode */
            analysisProfileCode?: string | null;
            /** Analysisprofileversion */
            analysisProfileVersion?: number | null;
            /** Catalogpricingprofilecode */
            catalogPricingProfileCode?: string | null;
            /** Catalogpricingprofileversion */
            catalogPricingProfileVersion?: number | null;
            /** Categorycode */
            categoryCode: string;
            /** Confirmationstatus */
            confirmationStatus: string;
            /** Confirmedat */
            confirmedAt?: string | null;
            /** Confirmedbyuserid */
            confirmedByUserId?: string | null;
            /** Createdat */
            createdAt?: string | null;
            /** Defaultunit */
            defaultUnit: string;
            /** Detections */
            detections?: components["schemas"]["VisionDetectionRead"][];
            /** Id */
            id: string;
            /** Itemsequence */
            itemSequence: number;
            /** Measuredquantity */
            measuredQuantity?: number | null;
            /** Measuredunit */
            measuredUnit?: string | null;
            /** Notes */
            notes?: string | null;
            /** Projectid */
            projectId: string;
            /** Settingversion */
            settingVersion?: number | null;
            /** Sourcetype */
            sourceType: string;
            /** Status */
            status: string;
            /** Tenantpricingprofileid */
            tenantPricingProfileId?: string | null;
            /** Title */
            title: string;
            /** Updatedat */
            updatedAt?: string | null;
            /** Values */
            values?: components["schemas"]["ProjectWorkItemValueRead"][];
            /** Worktypecode */
            workTypeCode: string;
            /** Worktypeversion */
            workTypeVersion: number;
        };
        /** ProjectWorkItemValueConfirmationInput */
        ProjectWorkItemValueConfirmationInput: {
            /** Action */
            action: string;
            /** Booleanvalue */
            booleanValue?: boolean | null;
            /** Numbervalue */
            numberValue?: number | null;
            /** Operatornote */
            operatorNote?: string | null;
            /** Optionvalue */
            optionValue?: string | null;
            /** Parametercode */
            parameterCode: string;
            /** Textvalue */
            textValue?: string | null;
        };
        /** ProjectWorkItemValueInput */
        ProjectWorkItemValueInput: {
            /** Booleanvalue */
            booleanValue?: boolean | null;
            /** Numbervalue */
            numberValue?: number | null;
            /** Operatornote */
            operatorNote?: string | null;
            /** Optionvalue */
            optionValue?: string | null;
            /** Parametercode */
            parameterCode: string;
            /** Sourceconfidence */
            sourceConfidence?: number | null;
            /** Sourcedetectionid */
            sourceDetectionId?: string | null;
            /**
             * Sourcetype
             * @default manual
             */
            sourceType: string;
            /** Textvalue */
            textValue?: string | null;
        };
        /** ProjectWorkItemValueRead */
        ProjectWorkItemValueRead: {
            /** Booleanvalue */
            booleanValue?: boolean | null;
            /** Confirmationstatus */
            confirmationStatus: string;
            /** Confirmedat */
            confirmedAt?: string | null;
            /** Confirmedbyuserid */
            confirmedByUserId?: string | null;
            /** Datatype */
            dataType: string;
            /** Manualoverrideallowed */
            manualOverrideAllowed?: boolean | null;
            /** Numbervalue */
            numberValue?: number | null;
            /** Operatornote */
            operatorNote?: string | null;
            /** Optionvalue */
            optionValue?: string | null;
            /** Parametercode */
            parameterCode: string;
            /** Parameterdefinitionid */
            parameterDefinitionId: string;
            /** Parameterlabel */
            parameterLabel: string;
            /**
             * Parameterscope
             * @default global
             */
            parameterScope: string;
            /** Parametersection */
            parameterSection?: string | null;
            /** Parameterslug */
            parameterSlug: string;
            /** Sourceconfidence */
            sourceConfidence?: number | null;
            /** Sourcedetectionid */
            sourceDetectionId?: string | null;
            /** Sourcetype */
            sourceType: string;
            /** Textvalue */
            textValue?: string | null;
            /** Unit */
            unit?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
            /** Visionextractable */
            visionExtractable?: boolean | null;
        };
        /** ProjectWorkItemWorkflowRead */
        ProjectWorkItemWorkflowRead: {
            /** Canconfirmvalues */
            canConfirmValues: boolean;
            /** Cancreatevisiondetections */
            canCreateVisionDetections: boolean;
            /** Canupdatevalues */
            canUpdateValues: boolean;
            /** Confirmedparametercodes */
            confirmedParameterCodes?: string[];
            /** Defaultedparametercodes */
            defaultedParameterCodes?: string[];
            /** Missingpricinginputcodes */
            missingPricingInputCodes?: string[];
            /** Missingrequiredparametercodes */
            missingRequiredParameterCodes?: string[];
            /** Pendingconfirmationparametercodes */
            pendingConfirmationParameterCodes?: string[];
            /** Supportspricing */
            supportsPricing: boolean;
            /** Supportsvision */
            supportsVision: boolean;
        };
        /** ProposalDraftField */
        ProposalDraftField: {
            /** Displayvalue */
            displayValue?: string | null;
            /**
             * Editable
             * @default true
             */
            editable: boolean;
            /** Id */
            id: string;
            /** Label */
            label: string;
            /**
             * Manualoverride
             * @default false
             */
            manualOverride: boolean;
            /** Source */
            source: string;
            /** Value */
            value?: string | number | null;
        };
        /** ProposalDraftItem */
        ProposalDraftItem: {
            /** Description */
            description?: string | null;
            /**
             * Editable
             * @default false
             */
            editable: boolean;
            /** Id */
            id: string;
            /** Label */
            label: string;
            /**
             * Manualoverride
             * @default false
             */
            manualOverride: boolean;
            /** Quantity */
            quantity?: number | null;
            /** Source */
            source: string;
            /** Totalprice */
            totalPrice?: number | null;
            /** Unit */
            unit?: string | null;
            /** Unitprice */
            unitPrice?: number | null;
        };
        /** ProposalDraftMaterial */
        ProposalDraftMaterial: {
            /** Name */
            name: string;
            /** Note */
            note?: string | null;
            /** Quantity */
            quantity: number;
            /** Totalprice */
            totalPrice: number;
            /** Unit */
            unit: string;
            /** Unitprice */
            unitPrice: number;
        };
        /** ProposalDraftSection */
        ProposalDraftSection: {
            /** Fields */
            fields?: components["schemas"]["ProposalDraftField"][];
            /** Id */
            id: string;
            /** Items */
            items?: components["schemas"]["ProposalDraftItem"][];
            /**
             * Kind
             * @enum {string}
             */
            kind: "fields" | "items";
            /** Title */
            title: string;
        };
        /** ProposalDraftWorkItem */
        ProposalDraftWorkItem: {
            /** Name */
            name: string;
            /** Note */
            note?: string | null;
        };
        /**
         * PurgePhotoRequest
         * @description Permanent deletion must be confirmed by repeating the photo id.
         */
        PurgePhotoRequest: {
            /** Confirmimageid */
            confirmImageId: string;
        };
        /** PurgePhotoResponse */
        PurgePhotoResponse: {
            /** Imageid */
            imageId: string;
            /**
             * Status
             * @enum {string}
             */
            status: "purged" | "purge_pending";
        };
        /** QuoteItemRead */
        QuoteItemRead: {
            /** Aisuggestedunitprice */
            aiSuggestedUnitPrice?: number | null;
            /** Catalogpricingprofilecode */
            catalogPricingProfileCode?: string | null;
            /** Catalogpricingprofileversion */
            catalogPricingProfileVersion?: number | null;
            /** Catalogpricingrulecode */
            catalogPricingRuleCode?: string | null;
            /** Companydefaultunitprice */
            companyDefaultUnitPrice?: number | null;
            /** Createdat */
            createdAt?: string | null;
            /** Description */
            description?: string | null;
            /** Id */
            id: string;
            /** Ismanualoverride */
            isManualOverride: boolean;
            /** Itemtype */
            itemType: string;
            /** Materialcatalogid */
            materialCatalogId?: string | null;
            /** Name */
            name: string;
            /** Pricesource */
            priceSource: string;
            /** Projectworkitemid */
            projectWorkItemId?: string | null;
            /** Quantity */
            quantity: number;
            /** Quotevariantid */
            quoteVariantId: string;
            /** Sortorder */
            sortOrder: number;
            /** Supplierid */
            supplierId?: string | null;
            /** Supplierreferenceunitprice */
            supplierReferenceUnitPrice?: number | null;
            /** Totalprice */
            totalPrice: number;
            /** Unit */
            unit: string;
            /** Unitprice */
            unitPrice: number;
            /** Updatedat */
            updatedAt?: string | null;
            /** Worktypecode */
            workTypeCode?: string | null;
        };
        /** QuoteVariantListResponse */
        QuoteVariantListResponse: {
            /** Items */
            items: components["schemas"]["QuoteVariantRead"][];
        };
        /** QuoteVariantRead */
        QuoteVariantRead: {
            /** Analysisresultid */
            analysisResultId?: string | null;
            /** Createdat */
            createdAt?: string | null;
            /** Currency */
            currency?: string | null;
            /** Id */
            id: string;
            /** Items */
            items: components["schemas"]["QuoteItemRead"][];
            /** Laborcost */
            laborCost: number;
            /** Marginpct */
            marginPct: number;
            /** Materialcost */
            materialCost: number;
            /** Othercost */
            otherCost: number;
            /** Pricingprofileid */
            pricingProfileId?: string | null;
            /** Projectid */
            projectId: string;
            /** Totalexvat */
            totalExVat: number;
            /** Totalincvat */
            totalIncVat: number;
            /** Updatedat */
            updatedAt?: string | null;
            /** Varianttype */
            variantType: string;
            /** Vatamount */
            vatAmount: number;
            /** Vatpct */
            vatPct?: number | null;
        };
        /** QuoteVariantRecalculateResponse */
        QuoteVariantRecalculateResponse: {
            /** Creatednew */
            createdNew?: boolean | null;
            /** Jobid */
            jobId?: string | null;
            /** Jobstatus */
            jobStatus?: string | null;
            /** Jobtype */
            jobType?: string | null;
            /** Variants */
            variants: components["schemas"]["QuoteVariantRecalculateSummary"][];
        };
        /** QuoteVariantRecalculateSummary */
        QuoteVariantRecalculateSummary: {
            /** Id */
            id: string;
            /** Totalincvat */
            totalIncVat: number;
            /** Varianttype */
            variantType: string;
        };
        /** RefreshRequest */
        RefreshRequest: {
            /** Refreshtoken */
            refreshToken: string;
        };
        /** ResetPasswordPayload */
        ResetPasswordPayload: {
            /** Password */
            password: string;
        };
        /** ResetPasswordResponse */
        ResetPasswordResponse: {
            /** Message */
            message: string;
        };
        /** RestorePhotoResponse */
        RestorePhotoResponse: {
            /** Message */
            message: string;
        };
        /** SecurityEventBatch */
        SecurityEventBatch: {
            /** Events */
            events: components["schemas"]["SecurityEventIn"][];
        };
        /** SecurityEventIn */
        SecurityEventIn: {
            /** Clientip */
            clientIp: string;
            /** Detail */
            detail?: {
                [key: string]: unknown;
            };
            /**
             * Occurredat
             * Format: date-time
             */
            occurredAt: string;
            /** Organizationid */
            organizationId?: string | null;
            /** Requestid */
            requestId?: string | null;
            /** Sessionref */
            sessionRef?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "login_success" | "login_failure" | "logout" | "logout_all" | "session_expired" | "session_revoked" | "csrf_failure" | "origin_failure" | "allowlist_miss" | "rate_limited" | "upstream_unavailable";
            /** Userid */
            userId?: string | null;
        };
        /** SecurityEventsAccepted */
        SecurityEventsAccepted: {
            /** Accepted */
            accepted: number;
        };
        /** SupplierPatch */
        SupplierPatch: {
            /** Contactemail */
            contactEmail?: string | null;
            /** Contactname */
            contactName?: string | null;
            /** Integrationtype */
            integrationType: string;
            /** Name */
            name: string;
            /** Websiteurl */
            websiteUrl?: string | null;
        };
        /** TenantWorkTypeExtraParameterOptionUpsert */
        TenantWorkTypeExtraParameterOptionUpsert: {
            /** Code */
            code: string;
            /**
             * Isactive
             * @default true
             */
            isActive: boolean;
            /** Label */
            label: string;
            /** Sortorder */
            sortOrder?: number | null;
        };
        /** TenantWorkTypeExtraParameterRead */
        TenantWorkTypeExtraParameterRead: {
            /** Code */
            code: string;
            /** Configversion */
            configVersion?: number | null;
            /** Datatype */
            dataType: string;
            /** Defaultbooleanvalue */
            defaultBooleanValue?: boolean | null;
            /** Defaultnumbervalue */
            defaultNumberValue?: number | null;
            /** Defaultoptioncode */
            defaultOptionCode?: string | null;
            /** Defaulttextvalue */
            defaultTextValue?: string | null;
            /** Description */
            description?: string | null;
            /** Enabled */
            enabled: boolean;
            /** Enumoptions */
            enumOptions?: components["schemas"]["WorkTypeParameterOptionRead"][];
            /** Label */
            label: string;
            /** Manualoverrideallowed */
            manualOverrideAllowed: boolean;
            /** Maxnumbervalue */
            maxNumberValue?: number | null;
            /** Minnumbervalue */
            minNumberValue?: number | null;
            /** Parameterdefinitionid */
            parameterDefinitionId: string;
            /**
             * Parameterscope
             * @default tenant_extra
             */
            parameterScope: string;
            /** Required */
            required: boolean;
            /** Section */
            section: string;
            /** Sectionlabel */
            sectionLabel: string;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
            /** Status */
            status: string;
            /** Unit */
            unit?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
            /** Visionextractable */
            visionExtractable: boolean;
        };
        /** TenantWorkTypeExtraParameterUpsert */
        TenantWorkTypeExtraParameterUpsert: {
            /** Code */
            code: string;
            /** Datatype */
            dataType: string;
            /** Defaultbooleanvalue */
            defaultBooleanValue?: boolean | null;
            /** Defaultnumbervalue */
            defaultNumberValue?: number | null;
            /** Defaultoptioncode */
            defaultOptionCode?: string | null;
            /** Defaulttextvalue */
            defaultTextValue?: string | null;
            /** Description */
            description?: string | null;
            /** Enumoptions */
            enumOptions?: components["schemas"]["TenantWorkTypeExtraParameterOptionUpsert"][];
            /** Label */
            label: string;
            /**
             * Manualoverrideallowed
             * @default true
             */
            manualOverrideAllowed: boolean;
            /** Maxnumbervalue */
            maxNumberValue?: number | null;
            /** Minnumbervalue */
            minNumberValue?: number | null;
            /**
             * Required
             * @default false
             */
            required: boolean;
            /** Section */
            section: string;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder?: number | null;
            /**
             * Status
             * @default active
             */
            status: string;
            /** Unit */
            unit?: string | null;
            /**
             * Visionextractable
             * @default false
             */
            visionExtractable: boolean;
        };
        /** TenantWorkTypeParameterOverrideRead */
        TenantWorkTypeParameterOverrideRead: {
            /** Configversion */
            configVersion?: number | null;
            /** Customdisplayname */
            customDisplayName?: string | null;
            /** Defaultbooleanvalue */
            defaultBooleanValue?: boolean | null;
            /** Defaultnumbervalue */
            defaultNumberValue?: number | null;
            /** Defaultoptioncode */
            defaultOptionCode?: string | null;
            /** Defaulttextvalue */
            defaultTextValue?: string | null;
            /** Overridestatus */
            overrideStatus: string;
            /** Parametercode */
            parameterCode: string;
            /** Sortorderoverride */
            sortOrderOverride?: number | null;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** TenantWorkTypeParameterOverrideUpsert */
        TenantWorkTypeParameterOverrideUpsert: {
            /** Customdisplayname */
            customDisplayName?: string | null;
            /** Defaultbooleanvalue */
            defaultBooleanValue?: boolean | null;
            /** Defaultnumbervalue */
            defaultNumberValue?: number | null;
            /** Defaultoptioncode */
            defaultOptionCode?: string | null;
            /** Defaulttextvalue */
            defaultTextValue?: string | null;
            /**
             * Overridestatus
             * @default inherited
             */
            overrideStatus: string;
            /** Parametercode */
            parameterCode: string;
            /** Sortorderoverride */
            sortOrderOverride?: number | null;
        };
        /** TenantWorkTypeSettingRead */
        TenantWorkTypeSettingRead: {
            /** Analysisprofilecode */
            analysisProfileCode?: string | null;
            /** Catalogpricingprofilecode */
            catalogPricingProfileCode?: string | null;
            /** Configversion */
            configVersion?: number | null;
            /** Customdisplayname */
            customDisplayName?: string | null;
            /** Isbillableoverride */
            isBillableOverride?: boolean | null;
            /** Sortorderoverride */
            sortOrderOverride?: number | null;
            /** Status */
            status: string;
            /** Tenantpricingprofileid */
            tenantPricingProfileId?: string | null;
            /** Updatedat */
            updatedAt?: string | null;
        };
        /** TenantWorkTypeSettingWithParametersUpsert */
        TenantWorkTypeSettingWithParametersUpsert: {
            /** Analysisprofilecode */
            analysisProfileCode?: string | null;
            /** Catalogpricingprofilecode */
            catalogPricingProfileCode?: string | null;
            /** Customdisplayname */
            customDisplayName?: string | null;
            /** Extraparameters */
            extraParameters?: components["schemas"]["TenantWorkTypeExtraParameterUpsert"][];
            /** Isbillableoverride */
            isBillableOverride?: boolean | null;
            /** Parameteroverrides */
            parameterOverrides?: components["schemas"]["TenantWorkTypeParameterOverrideUpsert"][];
            /** Sortorderoverride */
            sortOrderOverride?: number | null;
            /**
             * Status
             * @default enabled
             */
            status: string;
            /** Tenantpricingprofileid */
            tenantPricingProfileId?: string | null;
        };
        /**
         * TransitionRead
         * @description A single human-triggerable state machine action returned in the API response.
         */
        TransitionRead: {
            /** Action */
            action: string;
            /** Label */
            label: string;
            /** Requires Reason */
            requires_reason: boolean;
        };
        /** UploadedPhotoPayload */
        UploadedPhotoPayload: {
            /** Id */
            id: string;
            /** Isprimary */
            isPrimary: boolean;
            /** Processingstatus */
            processingStatus: string;
            /** Storagekey */
            storageKey: string;
            variants: components["schemas"]["PhotoVariants"];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** VisionDetectionCreate */
        VisionDetectionCreate: {
            /** Analysisjobid */
            analysisJobId?: string | null;
            /** Bboxbottom */
            bboxBottom?: number | null;
            /** Bboxleft */
            bboxLeft?: number | null;
            /** Bboxright */
            bboxRight?: number | null;
            /** Bboxtop */
            bboxTop?: number | null;
            /** Confidencescore */
            confidenceScore?: number | null;
            /** Detectedquantity */
            detectedQuantity?: number | null;
            /** Detectedunit */
            detectedUnit?: string | null;
            /** Detectionkey */
            detectionKey: string;
            /** Geometry */
            geometry?: unknown | null;
            /** Geometrytype */
            geometryType?: string | null;
            /** Rawlabel */
            rawLabel?: string | null;
            /** Rawvalue */
            rawValue?: string | null;
            /** Referencephotoid */
            referencePhotoId?: string | null;
            /** Sourcemodel */
            sourceModel?: string | null;
            /** Sourcemodelversion */
            sourceModelVersion?: string | null;
            /** Sourceprovider */
            sourceProvider?: string | null;
            /**
             * Status
             * @default pending
             */
            status: string;
            /** Worktypecode */
            workTypeCode: string;
        };
        /** VisionDetectionRead */
        VisionDetectionRead: {
            /** Bboxbottom */
            bboxBottom?: number | null;
            /** Bboxleft */
            bboxLeft?: number | null;
            /** Bboxright */
            bboxRight?: number | null;
            /** Bboxtop */
            bboxTop?: number | null;
            /** Confidencescore */
            confidenceScore?: number | null;
            /** Createdat */
            createdAt?: string | null;
            /** Detectedquantity */
            detectedQuantity?: number | null;
            /** Detectedunit */
            detectedUnit?: string | null;
            /** Detectionkey */
            detectionKey: string;
            /** Geometry */
            geometry?: unknown | null;
            /** Geometrytype */
            geometryType?: string | null;
            /** Id */
            id: string;
            /** Rawlabel */
            rawLabel?: string | null;
            /** Rawvalue */
            rawValue?: string | null;
            /** Referencephotoid */
            referencePhotoId?: string | null;
            /** Sourcemodel */
            sourceModel?: string | null;
            /** Sourcemodelversion */
            sourceModelVersion?: string | null;
            /** Sourceprovider */
            sourceProvider?: string | null;
            /** Status */
            status: string;
            /** Worktypecode */
            workTypeCode: string;
        };
        /** WorkCategoryRead */
        WorkCategoryRead: {
            /** Catalogversion */
            catalogVersion: number;
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
            /** Name Cs */
            name_cs?: string | null;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
        };
        /** WorkTypeParameterOptionRead */
        WorkTypeParameterOptionRead: {
            /** Code */
            code: string;
            /** Isactive */
            isActive: boolean;
            /** Label */
            label: string;
            /** Sortorder */
            sortOrder: number;
        };
        /** WorkTypeParameterRead */
        WorkTypeParameterRead: {
            /** Code */
            code: string;
            /** Datatype */
            dataType: string;
            /** Defaultbooleanvalue */
            defaultBooleanValue?: boolean | null;
            /** Defaultnumbervalue */
            defaultNumberValue?: number | null;
            /** Defaultoptioncode */
            defaultOptionCode?: string | null;
            /** Defaulttextvalue */
            defaultTextValue?: string | null;
            /** Description */
            description?: string | null;
            /** Effectivelabel */
            effectiveLabel: string;
            /**
             * Enabled
             * @default true
             */
            enabled: boolean;
            /** Enumoptions */
            enumOptions?: components["schemas"]["WorkTypeParameterOptionRead"][];
            /** Label */
            label: string;
            /** Manualoverrideallowed */
            manualOverrideAllowed: boolean;
            /** Maxnumbervalue */
            maxNumberValue?: number | null;
            /** Minnumbervalue */
            minNumberValue?: number | null;
            /** Overridestatus */
            overrideStatus?: string | null;
            /** Parameterdefinitionid */
            parameterDefinitionId: string;
            /**
             * Parameterscope
             * @default global
             */
            parameterScope: string;
            /** Required */
            required: boolean;
            /** Section */
            section: string;
            /** Sectionlabel */
            sectionLabel: string;
            /** Settingversion */
            settingVersion?: number | null;
            /** Slug */
            slug: string;
            /** Sortorder */
            sortOrder: number;
            /** Unit */
            unit?: string | null;
            /** Visionextractable */
            visionExtractable: boolean;
        };
        /** WorkTypeParameterSectionRead */
        WorkTypeParameterSectionRead: {
            /** Code */
            code: string;
            /** Label */
            label: string;
            /** Parameters */
            parameters?: components["schemas"]["WorkTypeParameterRead"][];
            /** Sortorder */
            sortOrder: number;
        };
        /** WorkTypePhaseBindingRead */
        WorkTypePhaseBindingRead: {
            /** Allowedcasestates */
            allowedCaseStates?: string[];
            /** Allowedincurrentcasestate */
            allowedInCurrentCaseState?: boolean | null;
            /** Currentcasestatus */
            currentCaseStatus?: string | null;
            /** Recommendedcasestates */
            recommendedCaseStates?: string[];
            /** Recommendedincurrentcasestate */
            recommendedInCurrentCaseState?: boolean | null;
            /** Visiondetectable */
            visionDetectable: boolean;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    root_api_v1__get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_audit_log_api_v1_admin_audit_get: {
        parameters: {
            query?: {
                action?: string | null;
                limit?: number;
                org_id?: string | null;
                user_id?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_companies_api_v1_admin_companies_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_company_api_v1_admin_companies_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_api_v1_admin_companies__company_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_company_api_v1_admin_companies__company_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    impersonate_user_api_v1_admin_impersonate__user_id__post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImpersonateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_all_jobs_api_v1_admin_jobs_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                org_id?: string | null;
                status?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_admin_job_api_v1_admin_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    admin_reprocess_dead_letter_job_api_v1_admin_jobs__job_id__reprocess_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    admin_retry_job_api_v1_admin_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_recent_logs_api_v1_admin_logs_get: {
        parameters: {
            query?: {
                lines?: number;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    admin_purge_photo_api_v1_admin_photos__photo_id__purge_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                photo_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PurgePhotoRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PurgePhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_users_api_v1_admin_users_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                org_id?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_user_api_v1_admin_users_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdminUserCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_user_api_v1_admin_users__user_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_user_api_v1_admin_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdminUserPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_user_password_api_v1_admin_users__user_id__reset_password_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResetPasswordPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    alive_api_v1_alive_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_analysis_job_api_v1_analysis_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_analysis_job_api_v1_analysis_jobs__job_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retry_analysis_job_api_v1_analysis_jobs__job_id__retry_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisTriggerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    change_password_api_v1_auth_change_password_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangePasswordResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    forgot_password_api_v1_auth_forgot_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForgotPasswordResponse"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LogoutRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LogoutResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RefreshRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_password_api_v1_auth_reset_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResetPasswordResponse"];
                };
            };
        };
    };
    list_sessions_api_v1_auth_sessions_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthSessionListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_session_api_v1_auth_sessions__session_id__delete: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LogoutResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_cases_api_v1_cases_get: {
        parameters: {
            query?: {
                /** @description Opaque cursor for next-page navigation */
                cursor?: string | null;
                limit?: number;
                /** @description Super-admin only: filter by organization */
                org_id?: string | null;
                search?: string | null;
                status?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_case_api_v1_cases_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_case_api_v1_cases__case_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_case_api_v1_cases__case_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_case_activity_api_v1_cases__case_id__activity_stream_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_case_analysis_jobs_api_v1_cases__case_id__analysis_jobs_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_analysis_job_api_v1_cases__case_id__analysis_jobs_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["AnalysisJobCreateRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisTriggerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_analysis_selection_api_v1_cases__case_id__analysis_results__result_id__selection_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                result_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_proposal_api_v1_cases__case_id__approve_proposal_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_case_api_v1_cases__case_id__archive_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_case_api_v1_cases__case_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    duplicate_case_api_v1_cases__case_id__duplicate_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectDuplicateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_case_estimates_api_v1_cases__case_id__estimates_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteVariantListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recalculate_case_estimates_api_v1_cases__case_id__estimates_recalculate_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuoteVariantRecalculateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_case_zip_api_v1_cases__case_id__exports_case_zip_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_proposal_docx_api_v1_cases__case_id__exports_proposal_docx_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_quote_docx_api_v1_cases__case_id__exports_quote_docx_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_quote_pdf_api_v1_cases__case_id__exports_quote_pdf_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_report_pdf_api_v1_cases__case_id__exports_report_pdf_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportCreateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_case_final_proposal_api_v1_cases__case_id__final_proposal_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_case_images_api_v1_cases__case_id__images_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhotoListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_case_images_api_v1_cases__case_id__images_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhotoUploadResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_case_image_api_v1_cases__case_id__images__image_id__delete: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletePhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_case_analysis_reference_image_api_v1_cases__case_id__images__image_id__analysis_reference_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisReferencePhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    move_case_image_api_v1_cases__case_id__images__image_id__move_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PhotoMoveRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PhotoListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    set_case_primary_image_api_v1_cases__case_id__images__image_id__primary_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrimaryPhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    purge_case_image_api_v1_cases__case_id__images__image_id__purge_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PurgePhotoRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PurgePhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    restore_case_image_api_v1_cases__case_id__images__image_id__restore_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RestorePhotoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_deleted_case_images_api_v1_cases__case_id__images_deleted_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletedPhotoListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_or_update_measurement_api_v1_cases__case_id__measurements_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeasurementUpsert"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasurementRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_case_proposal_draft_api_v1_cases__case_id__proposal_draft_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectProposalDraftPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    return_case_to_draft_api_v1_cases__case_id__return_to_draft_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_case_api_v1_cases__case_id__send_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_analysis_api_v1_cases__case_id__start_analysis_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_case_api_v1_cases__case_id__submit_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["CaseActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_case_timeline_api_v1_cases__case_id__timeline_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    }[];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_project_work_items_api_v1_cases__case_id__work_items_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_project_work_item_api_v1_cases__case_id__work_items_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectWorkItemCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_work_item_detail_api_v1_cases__case_id__work_items__project_work_item_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemDetailRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_vision_detection_api_v1_cases__case_id__work_items__project_work_item_id__detections_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VisionDetectionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VisionDetectionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    replace_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_put: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectWorkItemValueInput"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectWorkItemValueInput"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirm_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_confirm_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectWorkItemValueConfirmationInput"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    merge_project_work_item_values_api_v1_cases__case_id__work_items__project_work_item_id__values_merge_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                project_work_item_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectWorkItemValueInput"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_work_item_effective_configuration_api_v1_cases__case_id__work_types__work_type_code__effective_configuration_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                case_id: string;
                work_type_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectWorkItemEffectiveConfigurationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_export_api_v1_exports__export_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                export_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_export_file_api_v1_files_exports__export_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                export_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Celý soubor (Content-Type podle allowlistu, jinak application/octet-stream). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            /** @description Část souboru podle hlavičky Range (Content-Range). */
            206: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            /** @description Neexistuje, cizí firma, smazáno, nehotové nebo expirované. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Neplatný nebo nesplnitelný rozsah (Content-Range: bytes *\/<velikost>). */
            416: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_image_file_api_v1_files_images__image_id___variant__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                image_id: string;
                variant: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Celý soubor (Content-Type podle allowlistu, jinak application/octet-stream). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            /** @description Část souboru podle hlavičky Range (Content-Range). */
            206: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            /** @description Neexistuje, cizí firma, smazáno, nehotové nebo expirované. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Neplatný nebo nesplnitelný rozsah (Content-Range: bytes *\/<velikost>). */
            416: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_image_preview_api_v1_images__image_id__preview_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ingest_security_events_api_v1_internal_security_events_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SecurityEventBatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SecurityEventsAccepted"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_markers_api_v1_markers_get: {
        parameters: {
            query?: {
                case_id?: string | null;
                image_id?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarkerListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_marker_api_v1_markers_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarkerCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarkerRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_marker_api_v1_markers__marker_id__delete: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                marker_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarkerDeleteResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_material_catalog_api_v1_material_catalog_get: {
        parameters: {
            query?: {
                includeInactive?: boolean;
                search?: string | null;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_material_api_v1_material_catalog__material_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                material_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MaterialCatalogPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_supplier_prices_api_v1_material_catalog__material_id__supplier_prices_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                material_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_measurement_api_v1_measurements__measurement_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                measurement_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MeasurementUpsert"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasurementRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirm_measurement_api_v1_measurements__measurement_id__confirm_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                measurement_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeasurementRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_offer_request_api_v1_offer_requests_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferRequestCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferSubmitResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_offer_request_api_v1_offer_requests__offer_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferRequestRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_offer_api_v1_offer_requests__offer_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferApprove"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferStatusRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_offer_request_api_v1_offer_requests__offer_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferStatusRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_offer_events_api_v1_offer_requests__offer_id__events_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_more_info_api_v1_offer_requests__offer_id__more_info_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MoreInfoSubmit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferStatusRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_offer_result_api_v1_offer_requests__offer_id__result_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferResultRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_offer_status_api_v1_offer_requests__offer_id__status_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                offer_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OfferStatusRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_org_users_api_v1_org_users_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_org_user_api_v1_org_users_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrgUserCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_org_user_api_v1_org_users__user_id__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_org_user_api_v1_org_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrgUserPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    reset_org_user_password_api_v1_org_users__user_id__reset_password_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrgUserPasswordReset"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_pricebooks_api_v1_pricebooks_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PricebookListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_pricebook_api_v1_pricebooks_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PricebookCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PricebookRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_pricebook_items_api_v1_pricebooks__pricebook_id__items_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                pricebook_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PricebookItemRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ready_api_v1_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    ready_processing_api_v1_ready_processing_get: {
        parameters: {
            query?: {
                strict?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_suppliers_api_v1_suppliers_get: {
        parameters: {
            query?: {
                includeInactive?: boolean;
            };
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    patch_supplier_api_v1_suppliers__supplier_id__patch: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                supplier_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SupplierPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_catalog_categories_api_v1_work_catalog_catalog_categories_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogCategoryListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_catalog_grouped_api_v1_work_catalog_catalog_grouped_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogGroupedResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_catalog_work_types_api_v1_work_catalog_catalog_work_types_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogWorkTypeListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_catalog_work_type_detail_api_v1_work_catalog_catalog_work_types__work_type_code__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                work_type_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogWorkTypeDetailRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_parameter_schema_detail_api_v1_work_catalog_catalog_work_types__work_type_code__parameters__parameter_code__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                parameter_code: string;
                work_type_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ParameterSchemaDetailRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_effective_work_types_api_v1_work_catalog_work_types_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveWorkTypeListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_effective_work_type_api_v1_work_catalog_work_types__work_type_code__effective_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                work_type_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveWorkTypeRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upsert_tenant_work_type_setting_api_v1_work_catalog_work_types__work_type_code__settings_put: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                work_type_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantWorkTypeSettingWithParametersUpsert"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EffectiveWorkTypeRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    serve_storage_file_mock_storage__file_path__get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string;
            };
            path: {
                file_path: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
