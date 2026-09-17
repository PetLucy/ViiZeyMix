#include "intellipan_dsp.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define PI_F 3.14159265358979323846f

static float clampf(float value, float low, float high)
{
    return fmaxf(low, fminf(high, value));
}

static float soft_limit(float sample)
{
    return tanhf(sample * 0.85f) / tanhf(0.85f);
}

static int point_active(float x, float y)
{
    return fabsf(x) > 0.001f || fabsf(y) > 0.001f;
}

int intellipan_controls_active(const struct intellipan_controls *controls)
{
    return point_active(controls->color_x, controls->color_y) ||
        point_active(controls->modulation_x, controls->modulation_y) ||
        point_active(controls->position_x, controls->position_y);
}

static float process_color(
    float sample,
    float x,
    float y,
    struct intellipan_channel_state *state)
{
    if (!point_active(x, y))
        return sample;

    const float bass = fmaxf(0.0f, -x);
    const float mids = fmaxf(0.0f, x);
    const float treble = fmaxf(0.0f, y);
    const float warmth = fmaxf(0.0f, -y);
    const float bass_gain = 1.0f + bass * 1.35f;
    const float mid_gain = 1.0f + mids * 1.20f;
    const float high_gain = (1.0f + treble * 1.25f) * (1.0f - warmth * 0.62f);
    const float reverb_wet = treble * 0.12f;

    state->color_low_state += 0.018f * (sample - state->color_low_state);
    state->color_high_lp_state += 0.24f * (sample - state->color_high_lp_state);

    const float low = state->color_low_state;
    const float high = sample - state->color_high_lp_state;
    const float mid = state->color_high_lp_state - low;
    float colored = low * bass_gain + mid * mid_gain + high * high_gain;
    const float echo = state->color_delay[state->color_delay_pos];
    state->color_delay[state->color_delay_pos] = clampf(colored + echo * 0.28f, -1.5f, 1.5f);
    state->color_delay_pos = (state->color_delay_pos + 1) % IP_COLOR_REVERB_SAMPLES;
    colored = colored * (1.0f - reverb_wet) + echo * reverb_wet;
    return soft_limit(colored);
}

static float delayed_sample(
    const float *delay,
    uint32_t write_pos,
    float delay_samples)
{
    float read = (float)write_pos - delay_samples;
    while (read < 0.0f)
        read += (float)IP_MOD_DELAY_SAMPLES;
    const uint32_t first = (uint32_t)read % IP_MOD_DELAY_SAMPLES;
    const uint32_t second = (first + 1) % IP_MOD_DELAY_SAMPLES;
    const float fraction = read - floorf(read);
    return delay[first] * (1.0f - fraction) + delay[second] * fraction;
}

static float process_phaser(
    float sample,
    float coefficient,
    struct intellipan_channel_state *state)
{
    float value = sample;
    for (size_t stage = 0; stage < 4; ++stage) {
        const float output = -coefficient * value + state->phaser_state[stage];
        state->phaser_state[stage] = value + coefficient * output;
        value = output;
    }
    return value;
}

static float process_modulation(
    float sample,
    float x,
    float y,
    float lfo,
    uint32_t sample_rate,
    struct intellipan_channel_state *state)
{
    if (!point_active(x, y))
        return sample;

    const float depth = clampf(hypotf(x, y), 0.0f, 1.0f);
    const float bottom = fmaxf(0.0f, -y);
    const float top = fmaxf(0.0f, y);
    const float feedback = fmaxf(0.0f, -x) * depth * 0.68f;
    const float simple = fmaxf(0.0f, x);
    const float base_seconds = 0.006f + bottom * 0.007f;
    const float sweep_seconds = 0.0008f + depth * (0.0025f + top * 0.0025f);
    const float delay_samples = clampf(
        (base_seconds + sweep_seconds * (0.5f + 0.5f * lfo)) * (float)sample_rate,
        1.0f,
        (float)IP_MOD_DELAY_SAMPLES - 2.0f);
    const float delayed = delayed_sample(
        state->modulation_delay,
        state->modulation_delay_pos,
        delay_samples);

    state->modulation_delay[state->modulation_delay_pos] =
        clampf(sample + state->modulation_feedback_sample * feedback, -1.5f, 1.5f);
    state->modulation_delay_pos =
        (state->modulation_delay_pos + 1) % IP_MOD_DELAY_SAMPLES;
    state->modulation_feedback_sample = delayed;

    const float phaser_coefficient = clampf(0.28f + 0.55f * (0.5f + 0.5f * lfo), 0.1f, 0.88f);
    const float phased = process_phaser(sample, phaser_coefficient, state);
    const float bottom_wet = delayed * (0.68f + simple * 0.20f) + phased * 0.32f;
    const float tremolo = 1.0f - top * depth * 0.30f * (0.5f + 0.5f * lfo);
    const float top_wet = delayed * tremolo;
    const float family_mix = (y + 1.0f) * 0.5f;
    const float wet = bottom_wet * (1.0f - family_mix) + top_wet * family_mix;
    const float wet_mix = depth * (0.28f + bottom * 0.34f + top * 0.42f);
    return soft_limit(sample * (1.0f - wet_mix) + wet * wet_mix);
}

static void process_position(
    float left,
    float right,
    float x,
    float y,
    uint32_t sample_rate,
    struct intellipan_dsp_state *state,
    float *output_left,
    float *output_right)
{
    if (!point_active(x, y)) {
        *output_left = left;
        *output_right = right;
        return;
    }

    const float direction = clampf(x, -1.0f, 1.0f);
    const float distance = fmaxf(0.0f, y);
    const float width = fmaxf(0.0f, -y);
    const float mono = (left + right) * 0.5f;
    const float side = (left - right) * 0.5f * (1.0f + width * 0.65f);
    const float angle = (direction + 1.0f) * PI_F * 0.25f;
    const float left_gain = 0.22f + 0.78f * cosf(angle);
    const float right_gain = 0.22f + 0.78f * sinf(angle);
    float spatial_left = mono * left_gain + side * (1.0f - fabsf(direction) * 0.55f);
    float spatial_right = mono * right_gain - side * (1.0f - fabsf(direction) * 0.55f);

    const uint32_t delay_samples = (uint32_t)clampf(
        fabsf(direction) * 0.00065f * (float)sample_rate,
        0.0f,
        (float)IP_POSITION_DELAY_SAMPLES - 1.0f);
    const uint32_t read_pos =
        (state->position_delay_pos + IP_POSITION_DELAY_SAMPLES - delay_samples) %
        IP_POSITION_DELAY_SAMPLES;
    state->channels[0].position_delay[state->position_delay_pos] = spatial_left;
    state->channels[1].position_delay[state->position_delay_pos] = spatial_right;
    if (direction > 0.001f)
        spatial_left = state->channels[0].position_delay[read_pos];
    else if (direction < -0.001f)
        spatial_right = state->channels[1].position_delay[read_pos];

    const float shadow_amount = fabsf(direction) * 0.62f;
    const float shadow_coefficient = clampf(5200.0f / (float)sample_rate, 0.02f, 0.35f);
    if (direction > 0.001f) {
        struct intellipan_channel_state *far_ear = &state->channels[0];
        far_ear->head_shadow_state += shadow_coefficient * (spatial_left - far_ear->head_shadow_state);
        spatial_left = spatial_left * (1.0f - shadow_amount) + far_ear->head_shadow_state * shadow_amount;
    } else if (direction < -0.001f) {
        struct intellipan_channel_state *far_ear = &state->channels[1];
        far_ear->head_shadow_state += shadow_coefficient * (spatial_right - far_ear->head_shadow_state);
        spatial_right = spatial_right * (1.0f - shadow_amount) + far_ear->head_shadow_state * shadow_amount;
    }

    const uint32_t room_samples = (uint32_t)clampf(
        (0.018f + distance * 0.016f) * (float)sample_rate,
        1.0f,
        (float)IP_ROOM_DELAY_SAMPLES - 1.0f);
    const uint32_t room_read =
        (state->room_delay_pos + IP_ROOM_DELAY_SAMPLES - room_samples) % IP_ROOM_DELAY_SAMPLES;
    const float room_left = state->channels[0].room_delay[room_read];
    const float room_right = state->channels[1].room_delay[room_read];
    state->channels[0].room_delay[state->room_delay_pos] = clampf(spatial_left + room_right * 0.16f, -1.5f, 1.5f);
    state->channels[1].room_delay[state->room_delay_pos] = clampf(spatial_right + room_left * 0.16f, -1.5f, 1.5f);

    const float room_wet = 0.04f + distance * 0.18f;
    const float attenuation = 1.0f - distance * 0.34f;
    *output_left = soft_limit((spatial_left * (1.0f - room_wet) + room_right * room_wet) * attenuation);
    *output_right = soft_limit((spatial_right * (1.0f - room_wet) + room_left * room_wet) * attenuation);
}

void intellipan_dsp_process(
    float *output_left,
    float *output_right,
    const float *input_left,
    const float *input_right,
    uint32_t sample_count,
    uint32_t sample_rate,
    const struct intellipan_controls *controls,
    struct intellipan_dsp_state *state)
{
    if (output_left == NULL || output_right == NULL || controls == NULL || state == NULL)
        return;
    if (sample_rate == 0)
        sample_rate = 48000;
    if (!intellipan_controls_active(controls)) {
        if (input_left == NULL)
            memset(output_left, 0, sample_count * sizeof(float));
        else
            memcpy(output_left, input_left, sample_count * sizeof(float));
        if (input_right == NULL)
            memset(output_right, 0, sample_count * sizeof(float));
        else
            memcpy(output_right, input_right, sample_count * sizeof(float));
        return;
    }

    const float mod_depth = clampf(
        hypotf(controls->modulation_x, controls->modulation_y),
        0.0f,
        1.0f);
    const float mod_rate = 0.20f + mod_depth *
        (0.85f + fmaxf(0.0f, controls->modulation_y) * 5.5f +
         fmaxf(0.0f, controls->modulation_x) * 1.5f);
    const float phase_step = 2.0f * PI_F * mod_rate / (float)sample_rate;

    for (uint32_t index = 0; index < sample_count; ++index) {
        const float source_left = input_left == NULL ? 0.0f : input_left[index];
        const float source_right = input_right == NULL ? 0.0f : input_right[index];
        float left = process_color(
            source_left,
            controls->color_x,
            controls->color_y,
            &state->channels[0]);
        float right = process_color(
            source_right,
            controls->color_x,
            controls->color_y,
            &state->channels[1]);

        if (point_active(controls->modulation_x, controls->modulation_y)) {
            left = process_modulation(
                left,
                controls->modulation_x,
                controls->modulation_y,
                sinf(state->modulation_phase),
                sample_rate,
                &state->channels[0]);
            right = process_modulation(
                right,
                controls->modulation_x,
                controls->modulation_y,
                sinf(state->modulation_phase + PI_F * 0.5f),
                sample_rate,
                &state->channels[1]);
            state->modulation_phase += phase_step;
            if (state->modulation_phase >= 2.0f * PI_F)
                state->modulation_phase -= 2.0f * PI_F;
        }

        process_position(
            left,
            right,
            controls->position_x,
            controls->position_y,
            sample_rate,
            state,
            &output_left[index],
            &output_right[index]);
        state->position_delay_pos =
            (state->position_delay_pos + 1) % IP_POSITION_DELAY_SAMPLES;
        state->room_delay_pos = (state->room_delay_pos + 1) % IP_ROOM_DELAY_SAMPLES;
    }
}
