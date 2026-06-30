'use strict';

/**
 * @fileoverview Maestro — Pure Renderer Frontend (modularized)
 *
 * This file is the entry point for the Maestro frontend. It sets strict mode
 * and establishes the global namespace. All other JS files are loaded via
 * <script defer> in app.html — NOT ES modules — to preserve global scope
 * for inline onclick/oninput handlers.
 *
 * @author Maestro Engineering
 */

// ═══════════════════════════════════════════════════════════════════════════