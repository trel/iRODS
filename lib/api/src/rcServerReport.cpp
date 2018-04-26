#include "server_report.h"
#include "procApiRequest.h"
#include "apiNumber.h"

int
rcServerReport( rcComm_t *conn, bytesBuf_t** _bbuf ) {
    int status;
    status = procApiRequest( conn, SERVER_REPORT_AN, nullptr, nullptr,
                             ( void ** ) _bbuf, nullptr );

    return status;
}
