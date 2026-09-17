#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "intellipan_dsp.h"

#define TEST_RATE 48000U

static int neutral_is_exact_stereo_passthrough(void)
{
    const float left[] = {-0.9f, -0.25f, 0.0f, 0.3f, 0.95f};
    const float right[] = {0.7f, -0.2f, 0.1f, -0.8f, 0.4f};
    float output_left[5] = {0};
    float output_right[5] = {0};
    struct intellipan_controls controls = {0};
    struct intellipan_dsp_state *state = calloc(1, sizeof(*state));
    if (state == NULL)
        return 0;
    intellipan_dsp_process(
        output_left,
        output_right,
        left,
        right,
        5,
        TEST_RATE,
        &controls,
        state);
    const int passed =
        memcmp(left, output_left, sizeof(left)) == 0 &&
        memcmp(right, output_right, sizeof(right)) == 0;
    free(state);
    return passed;
}

static int color_changes_the_signal(void)
{
    const float input[] = {0.0f, 0.2f, -0.4f, 0.7f, -0.1f, 0.5f};
    float left[6] = {0};
    float right[6] = {0};
    struct intellipan_controls controls = {.color_x = -0.8f, .color_y = 0.6f};
    struct intellipan_dsp_state *state = calloc(1, sizeof(*state));
    if (state == NULL)
        return 0;
    intellipan_dsp_process(left, right, input, input, 6, TEST_RATE, &controls, state);
    int changed = 0;
    for (size_t index = 0; index < 6; ++index) {
        if (!isfinite(left[index]) || !isfinite(right[index])) {
            free(state);
            return 0;
        }
        if (fabsf(left[index] - input[index]) > 0.0001f)
            changed = 1;
    }
    free(state);
    return changed;
}

static int modulation_changes_and_stays_bounded(void)
{
    enum { SAMPLE_COUNT = 24000 };
    float *input = calloc(SAMPLE_COUNT, sizeof(float));
    float *left = calloc(SAMPLE_COUNT, sizeof(float));
    float *right = calloc(SAMPLE_COUNT, sizeof(float));
    struct intellipan_dsp_state *state = calloc(1, sizeof(*state));
    struct intellipan_controls controls = {
        .modulation_x = -1.0f,
        .modulation_y = 0.85f,
    };
    if (input == NULL || left == NULL || right == NULL || state == NULL) {
        free(input);
        free(left);
        free(right);
        free(state);
        return 0;
    }
    for (size_t index = 0; index < SAMPLE_COUNT; ++index)
        input[index] = 0.45f * sinf((float)index * 0.071f);
    intellipan_dsp_process(
        left,
        right,
        input,
        input,
        SAMPLE_COUNT,
        TEST_RATE,
        &controls,
        state);
    int changed = 0;
    int bounded = 1;
    for (size_t index = 1000; index < SAMPLE_COUNT; ++index) {
        if (!isfinite(left[index]) || !isfinite(right[index]) ||
            fabsf(left[index]) > 1.6f || fabsf(right[index]) > 1.6f) {
            bounded = 0;
            break;
        }
        if (fabsf(left[index] - input[index]) > 0.001f)
            changed = 1;
    }
    free(input);
    free(left);
    free(right);
    free(state);
    return changed && bounded;
}

static float channel_energy(const float *samples, size_t count)
{
    float energy = 0.0f;
    for (size_t index = 0; index < count; ++index)
        energy += samples[index] * samples[index];
    return energy;
}

static int position_moves_audio_toward_selected_side(void)
{
    enum { SAMPLE_COUNT = 512 };
    float input[SAMPLE_COUNT];
    float left[SAMPLE_COUNT] = {0};
    float right[SAMPLE_COUNT] = {0};
    struct intellipan_controls controls = {.position_x = -0.9f};
    struct intellipan_dsp_state *state = calloc(1, sizeof(*state));
    if (state == NULL)
        return 0;
    for (size_t index = 0; index < SAMPLE_COUNT; ++index)
        input[index] = 0.3f * sinf((float)index * 0.13f);
    intellipan_dsp_process(
        left,
        right,
        input,
        input,
        SAMPLE_COUNT,
        TEST_RATE,
        &controls,
        state);
    const int passed = channel_energy(left, SAMPLE_COUNT) > channel_energy(right, SAMPLE_COUNT) * 1.8f;
    free(state);
    return passed;
}

static int position_distance_adds_room_tail(void)
{
    enum { SAMPLE_COUNT = 2000 };
    float input[SAMPLE_COUNT];
    float left[SAMPLE_COUNT];
    float right[SAMPLE_COUNT];
    memset(input, 0, sizeof(input));
    memset(left, 0, sizeof(left));
    memset(right, 0, sizeof(right));
    input[0] = 0.8f;
    struct intellipan_controls controls = {.position_y = 1.0f};
    struct intellipan_dsp_state *state = calloc(1, sizeof(*state));
    if (state == NULL)
        return 0;
    intellipan_dsp_process(
        left,
        right,
        input,
        input,
        SAMPLE_COUNT,
        TEST_RATE,
        &controls,
        state);
    int tail = 0;
    for (size_t index = 1500; index < SAMPLE_COUNT; ++index) {
        if (fabsf(left[index]) > 0.0001f || fabsf(right[index]) > 0.0001f) {
            tail = 1;
            break;
        }
    }
    free(state);
    return tail;
}

int main(void)
{
    if (!neutral_is_exact_stereo_passthrough()) {
        fputs("neutral IntelliPan was not exact stereo passthrough\n", stderr);
        return 1;
    }
    if (!color_changes_the_signal()) {
        fputs("active Color did not change the signal\n", stderr);
        return 1;
    }
    if (!modulation_changes_and_stays_bounded()) {
        fputs("Modulation did not change the signal safely\n", stderr);
        return 1;
    }
    if (!position_moves_audio_toward_selected_side()) {
        fputs("Position did not move energy toward the selected side\n", stderr);
        return 1;
    }
    if (!position_distance_adds_room_tail()) {
        fputs("Position distance did not add a room tail\n", stderr);
        return 1;
    }
    puts("IntelliPan DSP tests passed");
    return 0;
}
