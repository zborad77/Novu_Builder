"use strict";

function buildNotReadyError(message, code) {
    const error = new Error(message);
    error.code = code;
    return error;
}

async function analyzeProject() {
    if (!process.env.OPENAI_API_KEY) {
        throw buildNotReadyError(
            "OpenAI vision provider needs OPENAI_API_KEY before it can be enabled.",
            "AI_PROVIDER_NOT_CONFIGURED"
        );
    }

    throw buildNotReadyError(
        "OpenAI vision provider is configured as a future integration point, but the real API call is not wired yet.",
        "AI_PROVIDER_NOT_IMPLEMENTED"
    );
}

module.exports = {
    key: "openai",
    analyzeProject
};
