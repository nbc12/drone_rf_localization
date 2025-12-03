% % File path
filename = 'test.dat';
fs = 10e6; 

% ==========================================
%      CONFIG
% ==========================================
median_rank = 51;       
power_threshold = 0.005; 

% ==========================================
%      LOAD DATA
% ==========================================
fid = fopen(filename, 'rb');
if fid == -1
    error('File not found: %s', filename);
end
raw_data = fread(fid, 'float32');
fclose(fid);

I = raw_data(1:2:end);
Q = raw_data(2:2:end);
iq = complex(I, Q);

% Create Sample Vector (Integers)
sample_axis = 1:length(iq);

% Original Windows (Seconds)
windows = [6.5937 6.5943;
           7.256 7.257;
           8.7561 8.7568;
           9.356128 9.35635];

figure('Color', 'w', 'Position', [100, 100, 1000, 800]);

for i = 1:size(windows, 1)
    
    % CONVERSION: Turn seconds into sample indices
    start_samp = max(1, floor(windows(i,1) * fs));
    end_samp   = min(length(iq), ceil(windows(i,2) * fs));
    idx_range = start_samp:end_samp;
    
    if isempty(idx_range)
        warning('Window %d is empty or out of bounds.', i);
        continue; 
    end
    
    % Extract Window Data
    s_win = sample_axis(idx_range);
    iq_win = iq(idx_range);
    
    % 1. RAW POWER
    raw_power = abs(iq_win).^2;
    
    % 2. MEDIAN FILTER (Trigger Source)
    len_p = length(raw_power);
    med_power = zeros(size(raw_power));
    half_win = floor(median_rank/2);
    
    for k = 1:len_p
        k_start = max(1, k - half_win);
        k_end   = min(len_p, k + half_win);
        med_power(k) = median(raw_power(k_start:k_end));
    end
    
    % ============================================================
    % 3. DYNAMIC ARRAY CONSTRUCTION
    % ============================================================
    pulse_plot = zeros(1, len_p);      
    sample_buffer = [];   
    is_in_pulse = false;
    pulse_start_idx = 0;
    
    % GUARD BAND: How many samples to ignore on edges?
    guard_samples = floor(median_rank / 2);
    
    for k = 1:len_p
        val = med_power(k); 
        
        if val > power_threshold
            % --- PULSE HIGH ---
            if ~is_in_pulse
                is_in_pulse = true;
                pulse_start_idx = k;
                sample_buffer = raw_power(k);
            else
                sample_buffer = [sample_buffer, raw_power(k)];
            end
        else
            % --- PULSE LOW ---
            if is_in_pulse
                is_in_pulse = false;
                
                % --- GUARD BAND LOGIC ---
                L = length(sample_buffer);
                if L > (2 * guard_samples)
                    buffer_trimmed = sample_buffer( (guard_samples + 1) : (L - guard_samples) );
                    avg_val = median(buffer_trimmed);
                else
                    avg_val = median(sample_buffer);
                end
                
                pulse_plot(pulse_start_idx : k-1) = avg_val;
                sample_buffer = [];
            end
        end
    end
    
    % EDGE CASE
    if is_in_pulse
        L = length(sample_buffer);
        if L > (2 * guard_samples)
            buffer_trimmed = sample_buffer((guard_samples + 1) : (L - guard_samples));
            avg_val = median(buffer_trimmed);
        else
            avg_val = median(sample_buffer);
        end
        pulse_plot(pulse_start_idx : end) = avg_val;
    end
    
    % ============================================================
    
    % --- PLOTTING ---
    subplot(2, 2, i);
    
    plot(s_win, raw_power, '-', 'Color', [0.8 0.8 0.8], 'LineWidth', 0.5);
    hold on;
    plot(s_win, med_power, 'k-', 'LineWidth', 1);
    yline(power_threshold, 'g--', 'LineWidth', 1);
    plot(s_win, pulse_plot, 'b-', 'LineWidth', 2);
    
    ylabel('Power');
    xlabel('Sample Index'); 
    
    % --- AXIS FORMAT FIX ---
    ax = gca;
    ax.XAxis.Exponent = 0;   % Disable the "x10^7" offset
    xtickformat('%.0f');     % Force full integer display
    % -----------------------
    
    title(sprintf('Window %d (Samples: %d-%d)', i, start_samp, end_samp));
    
    if max(med_power) > 0
        ylim([0, max(med_power)*1.3]);
    end
    grid on;
    
    if i == 1
        legend('Raw Power', 'Trigger (Median)', 'Threshold', 'Pulse (Trimmed Median)', ...
            'Location', 'northoutside', 'Orientation', 'horizontal');
    end
    hold off;
end
sgtitle(sprintf('Pulse Analysis (Rank: %d, Guard Band: %d samples)', median_rank, guard_samples));
