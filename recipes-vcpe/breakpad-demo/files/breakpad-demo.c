/*
 * breakpad-demo -- exercise breakpad/minidump on an RDK-B vCPE container
 *
 * Link with -lbreakpadwrapper; the library's constructor automatically
 * registers the Google Breakpad exception handler so any crash produces
 * a .dmp file under /minidumps/.
 *
 * Usage:
 *   breakpad-demo crash segv      # SIGSEGV  -> minidump
 *   breakpad-demo crash abort     # SIGABRT  -> minidump
 *   breakpad-demo crash null      # NULL deref -> minidump
 *   breakpad-demo crash divzero   # integer /0 -> minidump
 *   breakpad-demo crash stack     # stack overflow -> minidump
 *   breakpad-demo daemon          # background; kill -SEGV <pid> later
 *   breakpad-demo list            # show existing .dmp files
 *   breakpad-demo info            # show breakpad config / status
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <dirent.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <time.h>

/* breakpad_wrapper.h pulls in the C API; linking the .so triggers
   __attribute__((constructor)) breakpad_autoconstruct() which calls
   breakpad_ExceptionHandler() -- handler is live before main(). */
#include "breakpad_wrapper.h"

#define MINIDUMP_DIR "/minidumps"
#define PID_FILE     "/tmp/breakpad-demo.pid"

/* ------------------------------------------------------------------ */
/*  Crash helpers                                                      */
/* ------------------------------------------------------------------ */

static void crash_segv(void)
{
    printf("Triggering SIGSEGV...\n");
    fflush(stdout);
    raise(SIGSEGV);
}

static void crash_abort(void)
{
    printf("Triggering SIGABRT...\n");
    fflush(stdout);
    abort();
}

static void crash_null(void)
{
    volatile int *p = NULL;
    printf("Dereferencing NULL pointer...\n");
    fflush(stdout);
    *p = 42;
}

static void crash_divzero(void)
{
    volatile int a = 1;
    volatile int b = 0;
    printf("Dividing by zero...\n");
    fflush(stdout);
    a = a / b;
    (void)a;
}

static void crash_stack(void)
{
    volatile char buf[4096];
    buf[0] = 1;
    crash_stack();
}

/* ------------------------------------------------------------------ */
/*  Daemon mode                                                        */
/* ------------------------------------------------------------------ */

static void daemon_mode(void)
{
    FILE *fp;

    if (daemon(0, 0) != 0) {
        perror("daemon");
        exit(1);
    }

    fp = fopen(PID_FILE, "w");
    if (fp) {
        fprintf(fp, "%d\n", getpid());
        fclose(fp);
    }

    /* Sleep forever; send a signal to crash:
     *   kill -SEGV $(cat /tmp/breakpad-demo.pid)
     *   kill -ABRT $(cat /tmp/breakpad-demo.pid)
     */
    while (1)
        sleep(3600);
}

/* ------------------------------------------------------------------ */
/*  List / info                                                        */
/* ------------------------------------------------------------------ */

static void list_dumps(void)
{
    DIR *d = opendir(MINIDUMP_DIR);
    struct dirent *ent;
    int count = 0;

    if (!d) {
        printf("Cannot open %s\n", MINIDUMP_DIR);
        return;
    }

    printf("%-40s  %10s  %s\n", "File", "Size", "Modified");
    printf("%-40s  %10s  %s\n",
           "----------------------------------------",
           "----------",
           "-------------------");

    while ((ent = readdir(d)) != NULL) {
        char path[512];
        struct stat st;

        if (ent->d_name[0] == '.')
            continue;

        snprintf(path, sizeof(path), "%s/%s", MINIDUMP_DIR, ent->d_name);
        if (stat(path, &st) == 0) {
            char timebuf[64];
            struct tm *tm = localtime(&st.st_mtime);
            strftime(timebuf, sizeof(timebuf), "%Y-%m-%d %H:%M:%S", tm);
            printf("%-40s  %10ld  %s\n", ent->d_name, (long)st.st_size, timebuf);
            count++;
        }
    }
    closedir(d);

    if (count == 0)
        printf("(no dump files found)\n");
    else
        printf("\n%d dump file(s)\n", count);
}

static void show_info(void)
{
    printf("breakpad-demo info\n");
    printf("  PID:           %d\n", getpid());
    printf("  Minidump dir:  %s\n", MINIDUMP_DIR);
    printf("  PID file:      %s\n", PID_FILE);
    printf("  Handler:       registered by libbreakpadwrapper constructor\n");
    printf("\n");
    printf("To produce a minidump, run one of:\n");
    printf("  breakpad-demo crash segv\n");
    printf("  breakpad-demo crash abort\n");
    printf("  breakpad-demo crash null\n");
    printf("  breakpad-demo crash divzero\n");
    printf("  breakpad-demo crash stack\n");
    printf("  breakpad-demo daemon   (then: kill -SEGV $(cat %s))\n", PID_FILE);
}

/* ------------------------------------------------------------------ */
/*  Usage / main                                                       */
/* ------------------------------------------------------------------ */

static void usage(void)
{
    printf("Usage: breakpad-demo <command> [arg]\n");
    printf("\n");
    printf("Commands:\n");
    printf("  crash segv|abort|null|divzero|stack   Crash immediately\n");
    printf("  daemon                                Run in background\n");
    printf("  list                                  Show dump files\n");
    printf("  info                                  Show config\n");
}

int main(int argc, char *argv[])
{
    /* breakpad handler is already active (constructor in libbreakpadwrapper) */

    /* Pre-authorize ptrace from any process. Breakpad's signal handler
       clones a child that ptrace-attaches to us to write the minidump.
       Under Yama ptrace_scope=1 (default on Ubuntu/LXD hosts), the
       parent's prctl(PR_SET_PTRACER, child_pid) races with the child's
       ptrace(ATTACH) and often loses. Setting PR_SET_PTRACER_ANY here
       -- before any crash -- eliminates the race. */
    prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY);

    if (argc < 2) {
        usage();
        return 1;
    }

    if (strcmp(argv[1], "crash") == 0) {
        if (argc < 3) {
            printf("crash requires: segv|abort|null|divzero|stack\n");
            return 1;
        }
        if (strcmp(argv[2], "segv") == 0)        crash_segv();
        else if (strcmp(argv[2], "abort") == 0)   crash_abort();
        else if (strcmp(argv[2], "null") == 0)    crash_null();
        else if (strcmp(argv[2], "divzero") == 0) crash_divzero();
        else if (strcmp(argv[2], "stack") == 0)   crash_stack();
        else {
            printf("Unknown crash type: %s\n", argv[2]);
            return 1;
        }
    } else if (strcmp(argv[1], "daemon") == 0) {
        daemon_mode();
    } else if (strcmp(argv[1], "list") == 0) {
        list_dumps();
    } else if (strcmp(argv[1], "info") == 0) {
        show_info();
    } else {
        usage();
        return 1;
    }

    return 0;
}
