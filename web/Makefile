JS_DIR = js
CSS_DIR = css

JS_MIN = $(JS_DIR)/scripts.min.js
CSS_MIN = $(CSS_DIR)/styles.min.css

JS_MIN_FILES := $(sort $(patsubst %.js, %.min.js, $(filter-out %.min.js, $(wildcard $(JS_DIR)/*.js))))
CSS_MIN_FILES := $(sort $(patsubst %.css, %.min.css, $(filter-out %.min.css, $(wildcard $(CSS_DIR)/*.css))))

JS_COMPILER = utils/google-compiler --warning_level QUIET
CSS_COMPILER = utils/yuicompressor --type css

.PHONY: all clean

all: $(JS_MIN) $(CSS_MIN) utils/ServerExecute.class

%.min.js: %.js
	@echo "Compiling javascript" $<
	@$(JS_COMPILER) --js $< --js_output_file $@

%.min.css: %.css
	@echo "Compiling stylesheet" $<
	@$(CSS_COMPILER) -o $@ $<

$(JS_MIN): $(JS_MIN_FILES)
	@echo "Assembling compiled javascripts"
	@cat $^ > $@

$(CSS_MIN): $(CSS_MIN_FILES)
	@echo "Assembling compiled stylesheets"
	@cat $^ > $@

empty :=
space := $(empty) $(empty)
classpath := $(subst $(space),:,$(wildcard utils/htmlunit-2.8/*.jar))
utils/ServerExecute.class: utils/ServerExecute.java
	@echo "Building HtmlUnit wrapper."
	@javac -classpath $(classpath) -d utils $^

clean:
	@rm -fv $(JS_MIN) $(JS_MIN_FILES) $(CSS_MIN) $(CSS_MIN_FILES)

