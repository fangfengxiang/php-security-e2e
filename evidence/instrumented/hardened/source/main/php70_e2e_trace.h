/* Test-only Linux NTS observer. Never ship this build. */
#ifndef PHP70_E2E_TRACE_H
#define PHP70_E2E_TRACE_H
PHPAPI void php70_e2e_emit(const char *event, unsigned int detail);
PHPAPI void php70_e2e_begin(void);
PHPAPI void php70_e2e_rinit(void);
#endif
