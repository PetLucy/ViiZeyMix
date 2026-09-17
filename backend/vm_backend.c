#include <pipewire/pipewire.h>
#include <spa/utils/dict.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct app_state {
    struct pw_main_loop *loop;
    struct pw_context *context;
    struct pw_core *core;
    struct pw_registry *registry;
};

static void json_string(const char *s) {
    if (!s) {
        fputs("null", stdout);
        return;
    }

    fputc('"', stdout);
    for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
        switch (*p) {
            case '\\': fputs("\\\\", stdout); break;
            case '"':  fputs("\\\"", stdout); break;
            case '\n': fputs("\\n", stdout); break;
            case '\r': fputs("\\r", stdout); break;
            case '\t': fputs("\\t", stdout); break;
            default:
                if (*p < 0x20) {
                    fprintf(stdout, "\\u%04x", *p);
                } else {
                    fputc(*p, stdout);
                }
        }
    }
    fputc('"', stdout);
}

static const char *prop(const struct spa_dict *props, const char *key) {
    return props ? spa_dict_lookup(props, key) : NULL;
}

static int interesting_node(const struct spa_dict *props) {
    const char *media_class = prop(props, PW_KEY_MEDIA_CLASS);
    if (!media_class)
        return 0;

    return strstr(media_class, "Audio") != NULL;
}

static void registry_global(
    void *data,
    uint32_t id,
    uint32_t permissions,
    const char *type,
    uint32_t version,
    const struct spa_dict *props
) {
    (void)data;
    (void)permissions;
    (void)version;

    if (strcmp(type, PW_TYPE_INTERFACE_Node) != 0 || !interesting_node(props))
        return;

    printf("{");
    printf("\"id\":%u,", id);

    printf("\"name\":");
    json_string(prop(props, PW_KEY_NODE_NAME));
    printf(",");

    printf("\"description\":");
    json_string(prop(props, PW_KEY_NODE_DESCRIPTION));
    printf(",");

    printf("\"media_class\":");
    json_string(prop(props, PW_KEY_MEDIA_CLASS));
    printf(",");

    printf("\"application_name\":");
    json_string(prop(props, PW_KEY_APP_NAME));
    printf(",");

    printf("\"application_binary\":");
    json_string(prop(props, PW_KEY_APP_PROCESS_BINARY));
    printf(",");

    printf("\"media_name\":");
    json_string(prop(props, PW_KEY_MEDIA_NAME));

    printf("}\n");
    fflush(stdout);
}

static void registry_global_remove(void *data, uint32_t id) {
    (void)data;
    (void)id;
}

static const struct pw_registry_events registry_events = {
    PW_VERSION_REGISTRY_EVENTS,
    .global = registry_global,
    .global_remove = registry_global_remove,
};

static void core_done(void *data, uint32_t id, int seq) {
    struct app_state *state = data;
    (void)id;
    (void)seq;
    pw_main_loop_quit(state->loop);
}

static void core_error(
    void *data,
    uint32_t id,
    int seq,
    int res,
    const char *message
) {
    struct app_state *state = data;
    fprintf(stderr, "PipeWire core error: id=%u seq=%d res=%d: %s\n",
            id, seq, res, message ? message : "unknown");
    pw_main_loop_quit(state->loop);
}

static const struct pw_core_events core_events = {
    PW_VERSION_CORE_EVENTS,
    .done = core_done,
    .error = core_error,
};

int main(int argc, char **argv) {
    struct app_state state = {0};
    struct spa_hook registry_listener = {0};
    struct spa_hook core_listener = {0};

    pw_init(&argc, &argv);

    state.loop = pw_main_loop_new(NULL);
    if (!state.loop) {
        fprintf(stderr, "Could not create PipeWire main loop\n");
        return EXIT_FAILURE;
    }

    state.context = pw_context_new(pw_main_loop_get_loop(state.loop), NULL, 0);
    if (!state.context) {
        fprintf(stderr, "Could not create PipeWire context\n");
        pw_main_loop_destroy(state.loop);
        return EXIT_FAILURE;
    }

    state.core = pw_context_connect(state.context, NULL, 0);
    if (!state.core) {
        fprintf(stderr, "Could not connect to PipeWire\n");
        pw_context_destroy(state.context);
        pw_main_loop_destroy(state.loop);
        return EXIT_FAILURE;
    }

    pw_core_add_listener(state.core, &core_listener, &core_events, &state);

    state.registry = pw_core_get_registry(state.core, PW_VERSION_REGISTRY, 0);
    if (!state.registry) {
        fprintf(stderr, "Could not obtain PipeWire registry\n");
        pw_core_disconnect(state.core);
        pw_context_destroy(state.context);
        pw_main_loop_destroy(state.loop);
        return EXIT_FAILURE;
    }

    pw_registry_add_listener(
        state.registry,
        &registry_listener,
        &registry_events,
        &state
    );

    /*
     * A sync gives the registry time to enumerate existing globals.
     * core_done() quits the loop when that round trip completes.
     */
    pw_core_sync(state.core, PW_ID_CORE, 0);
    pw_main_loop_run(state.loop);

    spa_hook_remove(&registry_listener);
    spa_hook_remove(&core_listener);
    pw_proxy_destroy((struct pw_proxy *)state.registry);
    pw_core_disconnect(state.core);
    pw_context_destroy(state.context);
    pw_main_loop_destroy(state.loop);
    pw_deinit();

    return EXIT_SUCCESS;
}
